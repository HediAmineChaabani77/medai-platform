from __future__ import annotations

from pydantic import BaseModel, Field


class QARequest(BaseModel):
    question: str = Field(..., min_length=3, description="User question for medical QA")
    user_id: str | None = None


class QAResponse(BaseModel):
    answer: str
    provider_used: str
    model_used: str
    rule: str
    audit_id: int
    citations: list[dict] = Field(default_factory=list)

