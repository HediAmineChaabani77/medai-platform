import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.audit import append_audit, hash_patient_id, verify_chain
from app.db import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


def test_hash_patient_id_deterministic():
    h1 = hash_patient_id("PAT-123")
    h2 = hash_patient_id("PAT-123")
    assert h1 == h2 and len(h1) == 64
    assert hash_patient_id(None) is None


def test_append_and_chain_verification(db_session):
    k = "test-key"
    r1 = append_audit(db_session, k, event_type="llm_call", user_id="u1", patient_id="P1", use_case="UC1_DIAGNOSTIC", provider="local", model="llama", rule="R7_DEFAULT", latency_ms=120)
    r2 = append_audit(db_session, k, event_type="llm_call", user_id="u1", patient_id="P1", use_case="UC1_DIAGNOSTIC", provider="local", model="llama", rule="R7_DEFAULT", latency_ms=130)
    r3 = append_audit(db_session, k, event_type="routing", user_id="u1", use_case="UC2_REPORT", provider="cloud", rule="R5_COMPLEXITY")

    assert r2.prev_hash == r1.row_hash
    assert r3.prev_hash == r2.row_hash
    assert r1.patient_id_hash != "P1"  # never plaintext

    ok, broken = verify_chain(db_session, k)
    assert ok is True and broken is None


def test_chain_tamper_detected(db_session):
    k = "test-key"
    r1 = append_audit(db_session, k, event_type="llm_call", user_id="u1")
    r2 = append_audit(db_session, k, event_type="llm_call", user_id="u2")

    # Tamper: change a field post-insert.
    r1.user_id = "attacker"
    db_session.add(r1)
    db_session.commit()

    ok, broken = verify_chain(db_session, k)
    assert ok is False
    assert broken == r1.id


def test_wrong_key_rejects_chain(db_session):
    append_audit(db_session, "key-A", event_type="llm_call")
    ok, _ = verify_chain(db_session, "key-B")
    assert ok is False
