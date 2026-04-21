from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy.orm import Session

import app.models  # noqa: F401  # ensure model metadata registration
from app.config import Settings
from app.core.security import hash_password
from app.db import Base, engine
from app.models.drug import DrugInteraction
from app.models.model_registry import ModelVersion
from app.models.user import User


_INTERACTIONS_CSV = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "drug_interactions.csv"


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)


def seed_default_admin(db: Session, settings: Settings) -> None:
    if not settings.auth_dev_seed_admin:
        return
    row = db.query(User).filter(User.username == settings.auth_admin_username).first()
    if row:
        changed = False
        if row.role != "admin":
            row.role = "admin"
            changed = True
        if not row.totp_secret:
            row.totp_secret = settings.auth_admin_totp_secret
            changed = True
        if not row.active:
            row.active = True
            changed = True
        if changed:
            db.commit()
        return

    db.add(
        User(
            username=settings.auth_admin_username,
            password_hash=hash_password(settings.auth_admin_password),
            role="admin",
            totp_secret=settings.auth_admin_totp_secret,
            active=True,
        )
    )
    db.commit()


def seed_model_registry(db: Session, settings: Settings) -> None:
    # Local model row
    local = (
        db.query(ModelVersion)
        .filter(ModelVersion.provider == "local", ModelVersion.model_name == settings.llm_local_model)
        .first()
    )
    if not local:
        db.add(
            ModelVersion(
                provider="local",
                model_name=settings.llm_local_model,
                active=True,
                notes="seeded from settings",
            )
        )

    # Cloud model row
    cloud = (
        db.query(ModelVersion)
        .filter(ModelVersion.provider == "cloud", ModelVersion.model_name == settings.llm_cloud_model)
        .first()
    )
    if not cloud:
        db.add(
            ModelVersion(
                provider="cloud",
                model_name=settings.llm_cloud_model,
                active=True,
                notes="seeded from settings",
            )
        )
    db.commit()


def seed_drug_interactions(db: Session) -> int:
    """Upsert the curated drug interaction seed file into the `drug_interactions`
    table. Safe to call on every boot: existing (drug_a, drug_b, source) tuples
    are updated, new ones inserted. Returns number of rows upserted.
    """
    if not _INTERACTIONS_CSV.exists():
        return 0
    upserts = 0
    with _INTERACTIONS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            drug_a = (row.get("drug_a") or "").strip().lower()
            drug_b = (row.get("drug_b") or "").strip().lower()
            if not drug_a or not drug_b:
                continue
            src = (row.get("source") or "manual_seed").strip() or "manual_seed"
            severity = (row.get("severity") or "moderate").strip().lower()
            mechanism = row.get("mechanism") or ""
            note = row.get("note") or None
            existing = (
                db.query(DrugInteraction)
                .filter_by(drug_a=drug_a, drug_b=drug_b, source=src)
                .first()
            )
            if existing:
                changed = False
                if existing.severity != severity:
                    existing.severity = severity
                    changed = True
                if existing.mechanism != mechanism:
                    existing.mechanism = mechanism
                    changed = True
                if (existing.note or None) != note:
                    existing.note = note
                    changed = True
                if changed:
                    upserts += 1
            else:
                db.add(DrugInteraction(
                    drug_a=drug_a, drug_b=drug_b, severity=severity,
                    mechanism=mechanism, note=note, source=src,
                ))
                upserts += 1
    db.commit()
    return upserts

