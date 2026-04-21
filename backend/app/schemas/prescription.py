from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


Severity = Literal["minor", "moderate", "major"]


class Medication(BaseModel):
    name: str
    dose: str | None = None
    frequency: str | None = None
    duration: str | None = None
    route: str | None = None
    atc: str | None = None


class PatientProfile(BaseModel):
    age: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    pregnant: bool = False
    allergies: list[str] = Field(default_factory=list)
    current_medications: list[Medication] = Field(default_factory=list)
    dfg_ml_min: float | None = None
    liver_markers: dict | None = None
    # Comorbidity flags used by the contraindication checker.
    asthma: bool = False
    hepatic_failure: bool = False
    qt_ms: float | None = None
    kaliemia_mmol: float | None = None
    epilepsy: bool = False
    peptic_ulcer: bool = False


class PrescriptionRequest(BaseModel):
    new_medications: list[Medication]
    patient: PatientProfile
    patient_id: str | None = None
    physician_id: str | None = None
    department: str | None = None


class InteractionAlert(BaseModel):
    type: Literal["allergy", "contraindication", "interaction", "therapeutic_redundancy"]
    severity: Severity
    drug_a: str
    drug_b: str | None = None
    mechanism: str
    note: str | None = None


class PrescriptionResponse(BaseModel):
    blocked: bool
    max_severity: Severity | None
    alerts: list[InteractionAlert]
    explanation: str
    provider_used: str | None
    model_used: str | None
    rule: str | None
    audit_id: int | None
    alternatives: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
