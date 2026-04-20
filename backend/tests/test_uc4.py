import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from types import SimpleNamespace
from sqlalchemy.pool import StaticPool

from app.core.audit import append_audit
from app.core.security import require_admin_user
from app.db import Base, get_db
from app.main import app
from app.models.feedback import Feedback
from app.services.admin_service import compute_feedback_stats, compute_metrics


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


def test_metrics_empty(db):
    m = compute_metrics(db, window_hours=24)
    assert m.requests_total == 0
    assert m.cloud_cost_estimate_eur == 0.0


def test_metrics_counts(db):
    append_audit(db, "k", event_type="llm_call", provider="local", model="x", latency_ms=100)
    append_audit(db, "k", event_type="llm_call", provider="cloud", model="y", latency_ms=200)
    append_audit(db, "k", event_type="llm_call", provider="local", model="x", latency_ms=50)
    m = compute_metrics(db, window_hours=24)
    assert m.requests_total == 3
    assert m.requests_local == 2
    assert m.requests_cloud == 1
    assert m.avg_latency_ms_local == 75.0


def test_feedback_stats(db):
    for a in ("validate", "validate", "reject", "explain"):
        db.add(Feedback(use_case="UC1_DIAGNOSTIC", action=a))
    db.commit()
    s = compute_feedback_stats(db)
    assert s.validate == 2 and s.reject == 1 and s.explain == 1
    assert abs(s.rejection_rate - 0.25) < 1e-9


def test_rl_train_endpoint_is_501_stub():
    """RL is out of scope for the current phase per the PDF spec.
    The endpoint exists so admin tooling gets a deterministic 501 instead
    of a client-side 404, and the attempt is recorded in the audit log.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()

    def _get_db():
        try:
            yield s
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_admin_user] = lambda: SimpleNamespace(username="admin")
    client = TestClient(app)
    r = client.post("/api/admin/rl/train")
    assert r.status_code == 501
    body = r.json()
    assert "detail" in body and "Not Implemented" in body["detail"]
    app.dependency_overrides.clear()
    s.close()
