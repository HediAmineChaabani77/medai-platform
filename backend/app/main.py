from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.core.bootstrap import ensure_schema, seed_default_admin, seed_drug_interactions, seed_model_registry
from app.core.connectivity import ConnectivityProbe
from app.db import SessionLocal
from app.routes import auth, dmp, health, qa, uc1_diagnostic, uc2_report, uc3_prescription, uc4_admin


# Rate limiter keyed on client IP. Used by /auth/login.
limiter = Limiter(key_func=get_remote_address)


_DEFAULTS_REFUSE_IN_PROD = {
    "auth_admin_password": "admin123",
    "auth_admin_totp_secret": "JBSWY3DPEHPK3PXP",
    "jwt_secret": "jwt-secret-change-in-prod-xxxxxxxxxxxxxxxxxxxx",
    "audit_hmac_key": "audit-hmac-key-change-in-prod-xxxxxxxxxxxxxx",
    "app_secret": "change-me-in-production-min-32-chars-xxxxxxxxx",
}


def _assert_production_secrets(settings) -> None:
    """Refuse to boot in production if any default development secret is still
    in use. This stops accidental deployments with shipped credentials.
    """
    if settings.app_env != "production":
        return
    leaks = [k for k, default in _DEFAULTS_REFUSE_IN_PROD.items() if getattr(settings, k, None) == default]
    if leaks:
        raise RuntimeError(
            "Refusing to boot in APP_ENV=production with default dev secrets still set: "
            + ", ".join(sorted(leaks))
            + ". Rotate these via environment variables before deploying."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _assert_production_secrets(settings)
    if "PYTEST_CURRENT_TEST" not in os.environ:
        ensure_schema()
        with SessionLocal() as db:
            seed_default_admin(db, settings)
            seed_model_registry(db, settings)
            seed_drug_interactions(db)

    probe = ConnectivityProbe(get_settings())
    await probe.start()
    app.state.connectivity = probe
    try:
        yield
    finally:
        await probe.stop()


app = FastAPI(
    title="MedAI Assistant Platform",
    description="Hybrid local/cloud clinical assistant (HIPAA/GDPR scope)",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "rate_limited", "message": "Too many requests. Please retry later."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(dmp.router)
app.include_router(qa.router)
app.include_router(uc1_diagnostic.router)
app.include_router(uc2_report.router)
app.include_router(uc3_prescription.router)
app.include_router(uc4_admin.router)
