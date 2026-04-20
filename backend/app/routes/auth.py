from typing import Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.audit import append_audit
from app.core.bootstrap import seed_default_admin
from app.core.security import create_access_token, get_current_user_optional, verify_password
from app.db import get_db
from app.models.user import User
from app.schemas.auth import BootstrapAdminResponse, LoginRequest, LoginResponse

# Per-IP login limiter. Shared instance wired in `app.main` via `app.state.limiter`.
_limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_totp(user: User, code: Optional[str]) -> bool:
    if not user.totp_secret:
        return True
    if not code:
        return False
    return bool(pyotp.TOTP(user.totp_secret).verify(code, valid_window=1))


def _log_auth_event(db: Session, settings: Settings, *, username: Optional[str], event: str, ip: Optional[str]) -> None:
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type=event,
        user_id=username,
        payload={"ip": ip or "unknown"},
    )


@router.post("/login", response_model=LoginResponse)
@_limiter.limit(lambda: get_settings().auth_login_rate_limit)
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    client_ip = request.client.host if request.client else None
    user = db.query(User).filter(User.username == body.username, User.active.is_(True)).first()
    if not user or not verify_password(body.password, user.password_hash):
        _log_auth_event(db, settings, username=body.username, event="auth_login_failed", ip=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    requires_mfa = settings.admin_mfa_required and user.role == "admin"
    mfa_ok = _verify_totp(user, body.totp_code) if requires_mfa else True
    if requires_mfa and not mfa_ok:
        _log_auth_event(db, settings, username=user.username, event="auth_login_mfa_failed", ip=client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_totp")

    _log_auth_event(db, settings, username=user.username, event="auth_login_success", ip=client_ip)
    token = create_access_token(
        settings,
        sub=user.username,
        role=user.role,
        mfa_verified=bool(mfa_ok),
    )
    return LoginResponse(
        access_token=token,
        role=user.role,
        mfa_verified=bool(mfa_ok),
    )


@router.get("/me")
async def me(user: Optional[User] = Depends(get_current_user_optional)):
    if not user:
        return {"authenticated": False}
    claims = getattr(user, "_token_claims", {})
    return {
        "authenticated": True,
        "username": user.username,
        "role": user.role,
        "mfa_verified": bool(claims.get("mfa")),
    }


@router.post("/bootstrap-admin", response_model=BootstrapAdminResponse)
async def bootstrap_admin(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="disabled_in_production")
    seed_default_admin(db, settings)
    totp = pyotp.TOTP(settings.auth_admin_totp_secret)
    return BootstrapAdminResponse(
        username=settings.auth_admin_username,
        seeded=True,
        totp_secret=settings.auth_admin_totp_secret,
        totp_uri=totp.provisioning_uri(name=settings.auth_admin_username, issuer_name="MedAI Assistant"),
    )


@router.get("/dev/totp-now")
async def dev_totp_now(
    username: str = "admin",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="disabled_in_production")
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.totp_secret:
        raise HTTPException(status_code=404, detail="totp_secret_not_found")
    totp = pyotp.TOTP(user.totp_secret)
    return {"username": username, "totp_now": totp.now()}
