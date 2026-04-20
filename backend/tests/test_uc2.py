from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.llm_provider import LLMResponse
from app.db import Base
from app.schemas.report import ReportRequest
from app.services.report_service import TEMPLATES, archive_report, run_report, sign_report, _parse_markdown_sections


class FakeDispatcher:
    def __init__(self, text):
        self.text = text

    async def run(self, db, **kw):
        return SimpleNamespace(
            response=LLMResponse(text=self.text, model="llama3.1", provider="local"),
            provider_used="local",
            model_used="llama3.1",
            rule="R0_FORCE_LOCAL",
            reason="t",
            citations=[],
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


def test_templates_have_all_four_types():
    assert set(TEMPLATES) == {"Consultation", "Hospitalisation", "Opératoire", "Urgences"}


def test_parse_markdown_sections():
    md = "## Motif\nToux\n\n## Examen clinique\nRAS\n\n## Conclusion\nSuivi"
    sections = _parse_markdown_sections(md, ["Motif", "Examen clinique", "Conclusion"])
    assert [s.title for s in sections] == ["Motif", "Examen clinique", "Conclusion"]
    assert sections[0].content == "Toux"


def test_sign_report_deterministic_with_same_key():
    s1 = sign_report("texte", "key1")
    s2 = sign_report("texte", "key1")
    s3 = sign_report("texte", "key2")
    assert s1 == s2 and s1 != s3


@pytest.mark.asyncio
async def test_run_report_consultation(db):
    md = "## Motif\nToux sèche\n\n## Anamnèse\n5 jours\n\n## Examen clinique\nRAS\n\n## Conclusion\nVirale\n\n## Plan de soins\nAntitussifs"
    dispatcher = FakeDispatcher(md)
    req = ReportRequest(report_type="Consultation", raw_text="notes brutes", physician_id="dr1", physician_key="key1")
    resp = await run_report(db, dispatcher, req)
    assert resp.report_type == "Consultation"
    assert len(resp.sections) == 5
    assert resp.sections[0].title == "Motif"
    assert resp.signature


def test_archive_report_writes_row_and_path(db):
    row = archive_report(
        db,
        patient_id="P-123",
        report_type="Consultation",
        markdown="## Motif\nTest",
        signature="sig",
        signed_by="dr1",
    )
    assert row.id > 0
    assert row.archive_path
