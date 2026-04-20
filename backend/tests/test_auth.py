from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db import Base, get_db
from app.main import app
from app.models.user import User


def test_admin_login_totp_and_me():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    secret = "JBSWY3DPEHPK3PXP"
    s.add(
        User(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
            totp_secret=secret,
            active=True,
        )
    )
    s.commit()

    def _get_db():
        try:
            yield s
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app)

    # Wrong/missing totp rejected for admin when MFA required.
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 401

    code = pyotp.TOTP(secret).now()
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123", "totp_code": code})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["role"] == "admin"

    app.dependency_overrides.clear()
    s.close()
