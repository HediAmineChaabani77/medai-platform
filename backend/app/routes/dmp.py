from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.services.dmp_service import get_patient_from_dmp

router = APIRouter(prefix="/api/dmp", tags=["DMP"])


@router.get("/{patient_id}")
def get_patient_dmp(
    patient_id: str,
    settings: Settings = Depends(get_settings),
):
    record = get_patient_from_dmp(patient_id, settings)
    if not record:
        raise HTTPException(status_code=404, detail="patient_not_found_in_dmp")
    return {"patient_id": patient_id, "record": record}

