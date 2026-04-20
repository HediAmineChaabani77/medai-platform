from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.bootstrap import ensure_schema, seed_default_admin, seed_model_registry
from app.core.connectivity import ConnectivityProbe
from app.db import SessionLocal
from app.routes import auth, dmp, health, qa, uc1_diagnostic, uc2_report, uc3_prescription, uc4_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if "PYTEST_CURRENT_TEST" not in os.environ:
        ensure_schema()
        with SessionLocal() as db:
            seed_default_admin(db, settings)
            seed_model_registry(db, settings)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
