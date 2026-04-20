from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal


class RoutingPolicyIn(BaseModel):
    use_case: str
    department: str | None = None
    override: Literal["local", "cloud"]
    reason: str | None = None


class RoutingPolicyOut(RoutingPolicyIn):
    id: int
    created_at: datetime


class AuditLogOut(BaseModel):
    id: int
    created_at: datetime
    event_type: str
    user_id: str | None
    patient_id_hash: str | None
    use_case: str | None
    provider: str | None
    model: str | None
    rule: str | None
    latency_ms: int | None
    payload: dict | None


class Metrics(BaseModel):
    window_hours: int
    requests_total: int
    requests_local: int
    requests_cloud: int
    avg_latency_ms_local: float | None
    avg_latency_ms_cloud: float | None
    error_rate: float
    cloud_cost_estimate_eur: float


class FeedbackStats(BaseModel):
    validate: int
    reject: int
    explain: int
    rejection_rate: float
