from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.audit import append_audit, verify_chain
from app.config import Settings, get_settings
from app.core.security import require_admin_user
from app.db import get_db
from app.models.audit import AuditLog
from app.models.model_registry import ModelVersion, RLTrainingRun
from app.models.routing_policy import RoutingPolicy
from app.schemas.admin import AuditLogOut, FeedbackStats, Metrics, RoutingPolicyIn, RoutingPolicyOut
from app.services.admin_service import compute_feedback_stats, compute_metrics, run_rule_tuning

router = APIRouter(prefix="/api/admin", tags=["UC4-admin"])


@router.get("/metrics", response_model=Metrics)
def get_metrics(
    hours: int = 24,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    return compute_metrics(db, hours)


@router.get("/feedback-stats", response_model=FeedbackStats)
def get_feedback_stats(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    return compute_feedback_stats(db)


@router.get("/alerts")
def get_alerts(
    hours: int = 24,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    m = compute_metrics(db, hours)
    alerts: list[dict] = []
    if m.avg_latency_ms_local and m.avg_latency_ms_local > 35000:
        alerts.append({"level": "warn", "code": "local_latency_high", "message": f"Latence locale moyenne élevée ({m.avg_latency_ms_local:.0f} ms)."})
    if m.error_rate > 0.05:
        alerts.append({"level": "danger", "code": "error_rate_high", "message": f"Taux d'erreur élevé ({m.error_rate:.1%})."})
    if m.cloud_cost_estimate_eur > 15:
        alerts.append({"level": "warn", "code": "cloud_cost_high", "message": f"Coût cloud estimé élevé ({m.cloud_cost_estimate_eur:.2f} €)."})
    return {"window_hours": hours, "alerts": alerts}


@router.get("/routing-policies", response_model=list[RoutingPolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    return db.query(RoutingPolicy).order_by(RoutingPolicy.id.desc()).all()


@router.post("/routing-policies", response_model=RoutingPolicyOut, status_code=201)
def create_policy(
    body: RoutingPolicyIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin=Depends(require_admin_user),
):
    row = RoutingPolicy(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type="admin_policy_change",
        user_id=(admin.username if admin else None),
        use_case=body.use_case,
        payload={"action": "create", "policy_id": row.id, "override": body.override, "department": body.department},
    )
    return row


@router.delete("/routing-policies/{policy_id}")
def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin=Depends(require_admin_user),
):
    row = db.get(RoutingPolicy, policy_id)
    if not row:
        raise HTTPException(404, "not_found")
    db.delete(row)
    db.commit()
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type="admin_policy_change",
        user_id=(admin.username if admin else None),
        payload={"action": "delete", "policy_id": policy_id},
    )
    return {"deleted": policy_id}


@router.get("/audit", response_model=list[AuditLogOut])
def search_audit(
    patient_id_hash: str | None = None,
    use_case: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    q = db.query(AuditLog)
    if patient_id_hash:
        q = q.filter(AuditLog.patient_id_hash == patient_id_hash)
    if use_case:
        q = q.filter(AuditLog.use_case == use_case)
    if event_type:
        q = q.filter(AuditLog.event_type == event_type)
    return q.order_by(AuditLog.id.desc()).limit(limit).all()


@router.get("/audit/export")
def export_audit(
    fmt: str = "json",
    limit: int = 5000,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(20000, limit))).all()
    if fmt.lower() == "json":
        return [
            {
                "id": r.id,
                "created_at": r.created_at,
                "event_type": r.event_type,
                "user_id": r.user_id,
                "patient_id_hash": r.patient_id_hash,
                "use_case": r.use_case,
                "provider": r.provider,
                "model": r.model,
                "rule": r.rule,
                "latency_ms": r.latency_ms,
                "payload": r.payload,
            }
            for r in rows
        ]
    if fmt.lower() == "csv":
        buff = io.StringIO()
        w = csv.writer(buff)
        w.writerow(["id", "created_at", "event_type", "user_id", "patient_id_hash", "use_case", "provider", "model", "rule", "latency_ms"])
        for r in rows:
            w.writerow([r.id, r.created_at.isoformat() if r.created_at else "", r.event_type, r.user_id or "", r.patient_id_hash or "", r.use_case or "", r.provider or "", r.model or "", r.rule or "", r.latency_ms or ""])
        return Response(
            content=buff.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit_export.csv"'},
        )
    raise HTTPException(status_code=400, detail="fmt must be json or csv")


@router.get("/audit/verify")
def verify_audit(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin=Depends(require_admin_user),
):
    ok, broken = verify_chain(db, settings.audit_hmac_key)
    return {"ok": ok, "first_broken_id": broken}


@router.get("/models")
def list_models(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    local_active = db.query(ModelVersion).filter(ModelVersion.provider == "local", ModelVersion.active.is_(True)).first()
    cloud_active = db.query(ModelVersion).filter(ModelVersion.provider == "cloud", ModelVersion.active.is_(True)).first()
    return {
        "local": {
            "model": local_active.model_name if local_active else settings.llm_local_model,
            "host": settings.ollama_host,
            "embed_model": settings.llm_embed_model,
        },
        "cloud": {
            "provider": settings.llm_cloud_provider,
            "model": cloud_active.model_name if cloud_active else settings.llm_cloud_model,
            "base_url": settings.llm_cloud_base_url,
        },
        "force_local_only": settings.force_local_only,
    }


@router.get("/model-versions")
def list_model_versions(
    provider: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    q = db.query(ModelVersion)
    if provider in {"local", "cloud"}:
        q = q.filter(ModelVersion.provider == provider)
    rows = q.order_by(ModelVersion.id.desc()).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "provider": r.provider,
            "model_name": r.model_name,
            "notes": r.notes,
            "active": r.active,
        }
        for r in rows
    ]


@router.post("/model-versions")
def create_model_version(
    body: dict,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin=Depends(require_admin_user),
):
    provider = str(body.get("provider", "")).strip().lower()
    model_name = str(body.get("model_name", "")).strip()
    notes = body.get("notes")
    if provider not in {"local", "cloud"} or not model_name:
        raise HTTPException(status_code=400, detail="provider(local|cloud) and model_name are required")
    row = ModelVersion(provider=provider, model_name=model_name, notes=notes, active=bool(body.get("active", False)))
    if row.active:
        db.query(ModelVersion).filter(ModelVersion.provider == provider, ModelVersion.active.is_(True)).update({"active": False})
    db.add(row)
    db.commit()
    db.refresh(row)
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type="admin_model_version",
        user_id=(admin.username if admin else None),
        payload={"action": "create", "model_version_id": row.id, "provider": provider, "model_name": model_name, "active": row.active},
    )
    return {"id": row.id, "created": True}


@router.post("/model-versions/{version_id}/activate")
def activate_model_version(
    version_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin=Depends(require_admin_user),
):
    row = db.get(ModelVersion, version_id)
    if not row:
        raise HTTPException(status_code=404, detail="model_version_not_found")
    db.query(ModelVersion).filter(ModelVersion.provider == row.provider, ModelVersion.active.is_(True)).update({"active": False})
    row.active = True
    db.commit()
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type="admin_model_version",
        user_id=(admin.username if admin else None),
        payload={"action": "activate", "model_version_id": row.id, "provider": row.provider, "model_name": row.model_name},
    )
    return {"activated": row.id, "provider": row.provider, "model_name": row.model_name}


@router.post("/rl/train")
def rl_train(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin=Depends(require_admin_user),
):
    recommendations, summary = run_rule_tuning(db)
    run = RLTrainingRun(
        started_by=(admin.username if admin else None),
        status="completed",
        summary=summary,
        recommendations=recommendations,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type="rl_train_run",
        user_id=(admin.username if admin else None),
        payload={"run_id": run.id, "summary": summary, "recommendation_count": len(recommendations)},
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "summary": run.summary,
        "recommendations": run.recommendations or [],
    }
