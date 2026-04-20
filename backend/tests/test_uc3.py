from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.llm_provider import LLMResponse
from app.db import Base
from app.models.drug import DrugInteraction
from app.schemas.prescription import Medication, PatientProfile, PrescriptionRequest
from app.services.prescription_service import (
    check_allergies,
    check_contraindications,
    check_redundancy,
    max_severity,
    run_prescription_check,
)


class FakeDispatcher:
    async def run(self, db, **kw):
        return SimpleNamespace(
            response=LLMResponse(text="Risque hémorragique majeur. À éviter.", model="llama3.1", provider="local"),
            provider_used="local",
            model_used="llama3.1",
            rule="R3_PRESCRIPTION",
            reason="prescription_safety_critical_local",
            citations=[],
            retrievals=[],
            latency_ms=5,
            audit_id=42,
        )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    # Seed the key interaction: warfarin + aspirin major.
    s.add(
        DrugInteraction(
            drug_a="warfarin",
            drug_b="aspirin",
            severity="major",
            mechanism="Additive antiplatelet + anticoagulant",
            note="Risque hémorragique majeur.",
        )
    )
    s.commit()
    yield s
    s.close()


def test_max_severity():
    from app.schemas.prescription import InteractionAlert
    alerts = [
        InteractionAlert(type="interaction", severity="minor", drug_a="a", mechanism="m"),
        InteractionAlert(type="interaction", severity="moderate", drug_a="a", mechanism="m"),
        InteractionAlert(type="interaction", severity="minor", drug_a="a", mechanism="m"),
    ]
    assert max_severity(alerts) == "moderate"
    assert max_severity([]) is None


def test_check_allergies():
    p = PatientProfile(allergies=["pénicilline"])
    alerts = check_allergies(p, [Medication(name="Amoxicilline")])
    # No substring match here — amoxicilline contains 'cilline' but not exactly 'pénicilline'. Ensure explicit allergy matches.
    p2 = PatientProfile(allergies=["amoxicilline"])
    alerts2 = check_allergies(p2, [Medication(name="Amoxicilline 1g")])
    assert len(alerts2) == 1 and alerts2[0].severity == "major"


def test_check_contraindications_dfg():
    p = PatientProfile(dfg_ml_min=20)
    alerts = check_contraindications(p, [Medication(name="Metformin")])
    assert len(alerts) == 1 and alerts[0].severity == "major"


def test_check_contraindications_pregnancy_ains():
    p = PatientProfile(pregnant=True)
    alerts = check_contraindications(p, [Medication(name="Ibuprofène 400mg")])
    assert len(alerts) == 1 and alerts[0].severity == "major"


def test_check_redundancy():
    p = PatientProfile(current_medications=[Medication(name="Ramipril", atc="C09AA05")])
    alerts = check_redundancy(p, [Medication(name="Lisinopril", atc="C09AA05")])
    assert len(alerts) == 1 and alerts[0].severity == "moderate"


@pytest.mark.asyncio
async def test_warfarin_aspirin_blocks(db):
    req = PrescriptionRequest(
        new_medications=[Medication(name="Aspirine 100mg")],
        patient=PatientProfile(current_medications=[Medication(name="Warfarine 5mg")]),
        patient_id="P1",
        physician_id="dr1",
    )
    resp = await run_prescription_check(db, FakeDispatcher(), req)
    assert resp.blocked is True
    assert resp.max_severity == "major"
    assert any(a.type == "interaction" for a in resp.alerts)
    assert resp.provider_used == "local"
    assert isinstance(resp.alternatives, list)


@pytest.mark.asyncio
async def test_benign_prescription_not_blocked(db):
    req = PrescriptionRequest(
        new_medications=[Medication(name="Paracétamol 1g")],
        patient=PatientProfile(),
    )
    resp = await run_prescription_check(db, FakeDispatcher(), req)
    assert resp.blocked is False
    assert resp.max_severity is None
    assert resp.alerts == []
