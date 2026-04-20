import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.llm_provider import LLMResponse
from app.db import Base
from app.schemas.diagnostic import DiagnosticRequest, ExplainDiagnosticRequest
from app.services.diagnostic_service import run_diagnostic, run_diagnostic_explain


class FakeDispatcher:
    def __init__(self, text: str, provider="local", model="llama3.1", rule="R0_FORCE_LOCAL"):
        self.text = text
        self.provider = provider
        self.model = model
        self.rule = rule

    async def run(self, db, **kw):
        resp = LLMResponse(text=self.text, model=self.model, provider=self.provider)
        return SimpleNamespace(
            response=resp,
            provider_used=self.provider,
            model_used=self.model,
            rule=self.rule,
            reason="test",
            citations=[{"id": "SRC1", "source": "Vidal", "section": "x", "chunk_id": "c1", "metadata": {}}],
            retrievals=[],
            latency_ms=10,
            audit_id=1,
        )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


@pytest.mark.asyncio
async def test_uc1_parses_structured_json(db):
    answer = json.dumps(
        {
            "diagnoses": [
                {"condition": "Cystite simple", "probability": 0.7, "reasoning": "Dysurie + pollakiurie [SRC1]", "icd10": "N30", "citations": ["SRC1"]},
                {"condition": "Pyélonéphrite", "probability": 0.2, "reasoning": "Pas de fièvre", "icd10": "N10", "citations": []},
            ],
            "red_flags": ["fièvre > 38.5", "douleur lombaire"],
        }
    )
    dispatcher = FakeDispatcher(answer)
    req = DiagnosticRequest(symptoms="brûlures mictionnelles", patient_context={"age": 32, "sexe": "F"}, physician_id="dr1", patient_id="P1")
    resp = await run_diagnostic(db, dispatcher, req)
    assert len(resp.diagnoses) == 2
    assert resp.diagnoses[0].condition == "Cystite simple"
    assert resp.diagnoses[0].probability > resp.diagnoses[1].probability
    assert "fièvre > 38.5" in resp.red_flags
    assert resp.provider_used == "local"


@pytest.mark.asyncio
async def test_uc1_handles_prose_fallback(db):
    dispatcher = FakeDispatcher("Le patient souffre probablement d'une gastro-entérite virale.")
    req = DiagnosticRequest(symptoms="diarrhée", patient_context={})
    resp = await run_diagnostic(db, dispatcher, req)
    assert len(resp.diagnoses) >= 2
    assert resp.raw_answer.startswith("Le patient")


@pytest.mark.asyncio
async def test_uc1_explain_pair(db):
    dispatcher = FakeDispatcher("Option A est plus probable car la chronologie est compatible.")
    req = ExplainDiagnosticRequest(
        symptoms="douleur thoracique",
        option_a="Syndrome coronarien aigu",
        option_b="Reflux gastro-oesophagien",
    )
    resp = await run_diagnostic_explain(db, dispatcher, req)
    assert "Option A" in resp.explanation
    assert resp.provider_used == "local"


@pytest.mark.asyncio
async def test_uc1_filters_medication_like_diagnosis_and_repairs_red_flags(db):
    answer = json.dumps(
        {
            "diagnoses": [
                {"condition": "WARFARIN", "probability": 0.9, "reasoning": "bad", "icd10": None, "citations": []},
                {"diagnoses": [{"condition": "Syndrome coronarien aigu", "probability": 0.7, "reasoning": "douleur thoracique", "icd10": "I21", "citations": []}]},
            ],
            "red_flags": ["Désespoir respiratoire", "signal d urgence"],
        }
    )
    dispatcher = FakeDispatcher(answer)
    req = DiagnosticRequest(symptoms="douleur thoracique aiguë", patient_context={"age": 62, "sexe": "M"})
    resp = await run_diagnostic(db, dispatcher, req)
    names = [d.condition for d in resp.diagnoses]
    assert "WARFARIN" not in names
    assert any("coronarien" in n.lower() for n in names)
    assert any("dyspnée" in r.lower() or "thoracique" in r.lower() for r in resp.red_flags)
    assert "signal d urgence" not in [r.lower() for r in resp.red_flags]
