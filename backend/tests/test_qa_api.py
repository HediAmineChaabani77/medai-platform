from __future__ import annotations

from app.schemas.qa import QARequest, QAResponse


def test_qa_request_validation():
    body = QARequest(question="What is hypertension?")
    assert body.question == "What is hypertension?"


def test_qa_response_schema():
    resp = QAResponse(
        answer="Hypertension is elevated blood pressure.",
        provider_used="local",
        model_used="llama3.2:3b",
        rule="R0_FORCE_LOCAL",
        audit_id=1,
        citations=[{"id": "SRC1", "source": "medical_qa.json"}],
    )
    assert resp.provider_used == "local"
    assert resp.citations[0]["source"] == "medical_qa.json"

