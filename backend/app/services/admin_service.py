from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.feedback import Feedback
from app.schemas.admin import FeedbackStats, Metrics


CLOUD_PER_CALL_EUR = 0.002  # crude estimate


def compute_metrics(db: Session, window_hours: int = 24) -> Metrics:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    q = db.query(AuditLog).filter(AuditLog.created_at >= since, AuditLog.event_type == "llm_call")
    rows = q.all()
    local = [r for r in rows if r.provider == "local"]
    cloud = [r for r in rows if r.provider == "cloud"]

    def avg(values):
        xs = [v for v in values if v is not None]
        return (sum(xs) / len(xs)) if xs else None

    errors = sum(1 for r in rows if (r.payload or {}).get("error"))
    return Metrics(
        window_hours=window_hours,
        requests_total=len(rows),
        requests_local=len(local),
        requests_cloud=len(cloud),
        avg_latency_ms_local=avg([r.latency_ms for r in local]),
        avg_latency_ms_cloud=avg([r.latency_ms for r in cloud]),
        error_rate=(errors / len(rows)) if rows else 0.0,
        cloud_cost_estimate_eur=round(len(cloud) * CLOUD_PER_CALL_EUR, 4),
    )


def compute_feedback_stats(db: Session) -> FeedbackStats:
    agg = dict(
        db.query(Feedback.action, func.count(Feedback.id)).group_by(Feedback.action).all()
    )
    v = int(agg.get("validate", 0))
    r = int(agg.get("reject", 0))
    e = int(agg.get("explain", 0))
    total = v + r + e
    return FeedbackStats(validate=v, reject=r, explain=e, rejection_rate=(r / total) if total else 0.0)


def run_rule_tuning(db: Session) -> tuple[list[dict], dict]:
    """Heuristic policy recommendations from feedback + audit (future RL bootstrap)."""
    feedback_by_uc = dict(
        db.query(Feedback.use_case, func.count(Feedback.id))
        .filter(Feedback.action == "reject")
        .group_by(Feedback.use_case)
        .all()
    )
    llm_rows = db.query(AuditLog).filter(AuditLog.event_type == "llm_call").all()
    uc_totals: dict[str, int] = {}
    uc_avg_latency: dict[str, float] = {}
    for row in llm_rows:
        uc = row.use_case or "UNKNOWN"
        uc_totals[uc] = uc_totals.get(uc, 0) + 1
        if row.latency_ms is not None:
            uc_avg_latency.setdefault(uc, 0.0)
            uc_avg_latency[uc] += float(row.latency_ms)
    for uc, total in uc_totals.items():
        if total > 0 and uc in uc_avg_latency:
            uc_avg_latency[uc] = uc_avg_latency[uc] / total

    recommendations: list[dict] = []
    for uc, reject_count in sorted(feedback_by_uc.items(), key=lambda x: x[1], reverse=True):
        total = uc_totals.get(uc, 0)
        rejection_rate = (reject_count / total) if total else 0.0
        if rejection_rate >= 0.35 and total >= 3:
            recommendations.append(
                {
                    "use_case": uc,
                    "recommended_override": "local",
                    "reason": f"high_rejection_rate:{rejection_rate:.2f}",
                    "evidence": {"reject_count": reject_count, "total_calls": total},
                }
            )
    for uc, avg_ms in uc_avg_latency.items():
        if avg_ms > 35000:
            recommendations.append(
                {
                    "use_case": uc,
                    "recommended_override": "cloud",
                    "reason": f"latency_hotspot:{avg_ms:.0f}ms",
                    "evidence": {"avg_latency_ms": round(avg_ms, 1), "window_calls": uc_totals.get(uc, 0)},
                }
            )

    summary = {
        "total_llm_calls": len(llm_rows),
        "feedback_rows": db.query(func.count(Feedback.id)).scalar() or 0,
        "recommendation_count": len(recommendations),
    }
    return recommendations, summary
