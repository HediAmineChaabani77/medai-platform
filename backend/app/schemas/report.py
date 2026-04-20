from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


ReportType = Literal["Consultation", "Hospitalisation", "Opératoire", "Urgences"]


class ReportRequest(BaseModel):
    report_type: ReportType
    raw_text: str = Field("", description="Free-form notes or dictation transcription")
    patient_context: dict = Field(default_factory=dict)
    patient_id: str | None = None
    physician_id: str | None = None
    physician_key: str | None = Field(None, description="Electronic signing key for the physician")
    department: str | None = None


class ReportSection(BaseModel):
    title: str
    content: str


class ReportResponse(BaseModel):
    report_type: ReportType
    markdown: str
    sections: list[ReportSection]
    signature: str
    provider_used: str
    model_used: str
    rule: str
    audit_id: int
    citations: list[dict]


class ArchiveReportRequest(BaseModel):
    patient_id: str | None = None
    report_type: ReportType
    markdown: str
    signature: str
    signed_by: str | None = None
    destination: str = "DPI"


class ArchiveReportResponse(BaseModel):
    archive_id: int
    destination: str
    archive_path: str
