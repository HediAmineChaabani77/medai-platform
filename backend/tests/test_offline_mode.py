"""Proves UC1, UC2, UC3 remain functional with connectivity disabled.

Patches the ConnectivityProbe to report offline, mocks the local Ollama HTTP API,
and stubs RAG retrieval. Verifies every use case returns a valid response and
that every LLM call routes to provider='local' with rule R0_FORCE_LOCAL or R1_OFFLINE.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.audit import append_audit
from app.core.dispatcher import LLMDispatcher
from app.core.llm_provider import LLMResponse
from app.core.phi_detector import PHIDetector
from app.core.rag import Chunk, Retrieval
from app.core.router import Router, UseCase
from app.db import Base
from app.models.drug import DrugInteraction
from app.schemas.diagnostic import DiagnosticRequest
from app.schemas.prescription import Medication, PatientProfile, PrescriptionRequest
from app.schemas.report import ReportRequest
from app.services.diagnostic_service import run_diagnostic
from app.services.prescription_service import run_prescription_check
from app.services.report_service import run_report


class OfflineConn:
    def is_online(self):
        return False


class NoPolicy:
    def override_for(self, *a, **k):
        return None


class ZeroLoad:
    def local_queue_depth(self):
        return 0


class StubRAG:
    async def retrieve(self, query, top_k=5):
        return [
            Retrieval(
                chunk=Chunk(id="stub:0", text="Extrait local (hors ligne).", metadata={"source": "KB-local", "section": "Offline"}),
                score=1.0,
            )
        ]


class FakeLocal:
    name = "local"
    model = "llama3.1:8b-instruct"
    provider = "local"

    def __init__(self, response_text: str):
        self.response_text = response_text

    async def generate(self, prompt, system=None, max_tokens=512, temperature=0.2, format=None):
        return LLMResponse(text=self.response_text, model=self.model, provider="local")

    async def embed(self, text):
        return [0.0] * 768


class FakeCloud:
    """Raises on any call. Proves cloud is never invoked offline."""
    name = "cloud"
    model = "never"
    provider = "cloud"

    async def generate(self, *a, **k):
        raise AssertionError("cloud_provider_must_not_be_called_offline")

    async def embed(self, *a, **k):
        raise AssertionError("cloud_embed_must_not_be_called_offline")


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    s.add(DrugInteraction(drug_a="warfarin", drug_b="aspirin", severity="major", mechanism="Addition", note="block"))
    s.commit()
    yield s
    s.close()


def _dispatcher(local_text: str, force_local=False):
    router = Router(
        connectivity=OfflineConn(),
        phi=PHIDetector(nlp=False),
        policy=NoPolicy(),
        load=ZeroLoad(),
        force_local_only=force_local,
    )
    return LLMDispatcher(
        router=router,
        local_provider=FakeLocal(local_text),
        cloud_provider=FakeCloud(),
        rag=StubRAG(),
        hmac_key="offline-key",
    )


@pytest.mark.asyncio
async def test_uc1_offline(db):
    dispatcher = _dispatcher(json.dumps({"diagnoses": [{"condition": "Rhinite", "probability": 0.6, "reasoning": "r", "icd10": "J30", "citations": ["SRC1"]}], "red_flags": []}))
    req = DiagnosticRequest(symptoms="éternuements", patient_context={"age": 30}, physician_id="dr1", patient_id="P1")
    resp = await run_diagnostic(db, dispatcher, req)
    assert resp.provider_used == "local"
    assert resp.rule == "R1_OFFLINE"
    assert len(resp.diagnoses) == 1


@pytest.mark.asyncio
async def test_uc2_offline(db):
    md = "## Motif\nToux\n\n## Anamnèse\n3j\n\n## Examen clinique\nRAS\n\n## Conclusion\nViral\n\n## Plan de soins\nRepos"
    dispatcher = _dispatcher(md)
    req = ReportRequest(report_type="Consultation", raw_text="toux 3 jours", physician_id="dr1", physician_key="k")
    resp = await run_report(db, dispatcher, req)
    assert resp.provider_used == "local"
    assert resp.rule == "R1_OFFLINE"
    assert len(resp.sections) == 5


@pytest.mark.asyncio
async def test_uc3_offline_blocks_major(db):
    dispatcher = _dispatcher("Explication: éviter la combinaison [SRC1].")
    req = PrescriptionRequest(
        new_medications=[Medication(name="Aspirine 100mg")],
        patient=PatientProfile(current_medications=[Medication(name="Warfarine 5mg")]),
        patient_id="P1",
        physician_id="dr1",
    )
    resp = await run_prescription_check(db, dispatcher, req)
    assert resp.blocked is True
    assert resp.max_severity == "major"
    assert resp.provider_used == "local"
    # UC3 is always local via R3 — or via R1 since we're offline. Both acceptable.
    assert resp.rule in {"R1_OFFLINE", "R3_PRESCRIPTION"}


@pytest.mark.asyncio
async def test_audit_rows_written_per_call(db):
    """Every UC LLM call must produce exactly one audit row."""
    from app.models.audit import AuditLog
    before = db.query(AuditLog).count()

    dispatcher = _dispatcher(json.dumps({"diagnoses": [], "red_flags": []}))
    await run_diagnostic(db, dispatcher, DiagnosticRequest(symptoms="x", patient_context={}))
    after = db.query(AuditLog).count()
    assert after == before + 1
