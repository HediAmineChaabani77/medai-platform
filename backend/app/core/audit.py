from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


GENESIS_HASH = "0" * 64


def hash_patient_id(patient_id: str | None) -> str | None:
    if not patient_id:
        return None
    return hashlib.sha256(patient_id.encode("utf-8")).hexdigest()


def _canonical_payload(**fields: Any) -> str:
    return json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _iso_utc(dt: datetime) -> str:
    """Render a datetime as ISO 8601 UTC. Tolerates naive datetimes returned
    by SQLite, which drops tzinfo on round-trip, by assuming UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _compute_row_hash(hmac_key: str, prev_hash: str, fields: dict[str, Any]) -> str:
    body = _canonical_payload(prev_hash=prev_hash, **fields)
    return hmac.new(hmac_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def append_audit(
    db: Session,
    hmac_key: str,
    *,
    event_type: str,
    user_id: str | None = None,
    patient_id: str | None = None,
    use_case: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    rule: str | None = None,
    latency_ms: int | None = None,
    payload: dict | None = None,
) -> AuditLog:
    """Append a tamper-evident row. Returns the persisted AuditLog."""
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last.row_hash if last else GENESIS_HASH

    created_at = datetime.now(timezone.utc)
    fields = {
        "created_at": _iso_utc(created_at),
        "event_type": event_type,
        "user_id": user_id,
        "patient_id_hash": hash_patient_id(patient_id),
        "use_case": use_case,
        "provider": provider,
        "model": model,
        "rule": rule,
        "latency_ms": latency_ms,
        "payload": payload,
    }
    row_hash = _compute_row_hash(hmac_key, prev_hash, fields)

    row = AuditLog(
        created_at=created_at,
        event_type=event_type,
        user_id=user_id,
        patient_id_hash=fields["patient_id_hash"],
        use_case=use_case,
        provider=provider,
        model=model,
        rule=rule,
        latency_ms=latency_ms,
        payload=payload,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def verify_chain(db: Session, hmac_key: str) -> tuple[bool, int | None]:
    """Replay HMAC from genesis. Returns (ok, first_broken_id)."""
    prev_hash = GENESIS_HASH
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    for row in rows:
        if row.prev_hash != prev_hash:
            return False, row.id
        fields = {
            "created_at": _iso_utc(row.created_at),
            "event_type": row.event_type,
            "user_id": row.user_id,
            "patient_id_hash": row.patient_id_hash,
            "use_case": row.use_case,
            "provider": row.provider,
            "model": row.model,
            "rule": row.rule,
            "latency_ms": row.latency_ms,
            "payload": row.payload,
        }
        expected = _compute_row_hash(hmac_key, prev_hash, fields)
        if expected != row.row_hash:
            return False, row.id
        prev_hash = row.row_hash
    return True, None
