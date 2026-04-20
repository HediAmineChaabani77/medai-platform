from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(
    settings: Settings,
    *,
    sub: str,
    role: str,
    mfa_verified: bool,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "role": role,
        "mfa": mfa_verified,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_exp_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token") from e


def _read_user_from_token(db: Session, settings: Settings, token: str) -> User:
    payload = decode_access_token(settings, token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_subject")
    user = db.query(User).filter(User.username == str(sub), User.active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found_or_inactive")
    # Attach claims for downstream checks without re-decoding.
    setattr(user, "_token_claims", payload)
    return user


def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if creds is None:
        return None
    return _read_user_from_token(db, settings, creds.credentials)


def require_admin_user(
    user: User | None = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if user is None:
        if settings.admin_auth_required:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin_auth_required")
        return None
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_role_required")
    if settings.admin_mfa_required and not bool(getattr(user, "_token_claims", {}).get("mfa")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_mfa_required")
    return user
