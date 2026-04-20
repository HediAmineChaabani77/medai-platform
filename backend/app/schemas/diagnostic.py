from __future__ import annotations

from pydantic import BaseModel, Field


class DiagnosticRequest(BaseModel):
    symptoms: str = Field(..., description="Free-text symptom description from physician")
    patient_context: dict = Field(default_factory=dict)
    patient_id: str | None = None
    physician_id: str | None = None
    department: str | None = None


class DiagnosticCandidate(BaseModel):
    condition: str
    probability: float
    reasoning: str
    icd10: str | None = None
    citations: list[str] = Field(default_factory=list)


class DiagnosticResponse(BaseModel):
    diagnoses: list[DiagnosticCandidate]
    red_flags: list[str] = Field(default_factory=list)
    provider_used: str
    model_used: str
    rule: str
    audit_id: int
    citations: list[dict]
    raw_answer: str


class FeedbackRequest(BaseModel):
    audit_log_id: int | None = None
    use_case: str
    action: str  # validate | reject | explain
    note: str | None = None
    context: dict = Field(default_factory=dict)
    user_id: str | None = None


class ExplainDiagnosticRequest(BaseModel):
    symptoms: str
    option_a: str
    option_b: str
    patient_context: dict = Field(default_factory=dict)
    patient_id: str | None = None
    physician_id: str | None = None
    department: str | None = None


class ExplainDiagnosticResponse(BaseModel):
    explanation: str
    provider_used: str
    model_used: str
    rule: str
    audit_id: int
