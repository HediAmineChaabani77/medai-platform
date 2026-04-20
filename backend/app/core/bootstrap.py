from __future__ import annotations

from sqlalchemy.orm import Session

import app.models  # noqa: F401  # ensure model metadata registration
from app.config import Settings
from app.core.security import hash_password
from app.db import Base, engine
from app.models.model_registry import ModelVersion
from app.models.user import User


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

