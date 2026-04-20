from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.audit import append_audit
from app.core.dispatcher import LLMDispatcher
from app.db import get_db
from app.deps import get_dispatcher
from app.models.report_archive import ReportArchive
from app.schemas.report import ArchiveReportRequest, ArchiveReportResponse, ReportRequest, ReportResponse
from app.services.report_service import archive_report, run_report, transcribe_audio_local

router = APIRouter(prefix="/api/uc2", tags=["UC2-report"])


@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    body: ReportRequest,
    db: Session = Depends(get_db),
    dispatcher: LLMDispatcher = Depends(get_dispatcher),
):
    return await run_report(db, dispatcher, body)


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("fr")):
    """Local Whisper transcription. Runs offline."""
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await audio.read())
        path = Path(tmp.name)
    try:
        text = transcribe_audio_local(path, language=language)
    finally:
        path.unlink(missing_ok=True)
    return {"text": text}


@router.post("/archive", response_model=ArchiveReportResponse)
async def archive(
    body: ArchiveReportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    row = archive_report(
        db,
        patient_id=body.patient_id,
        report_type=body.report_type,
        markdown=body.markdown,
        signature=body.signature,
        signed_by=body.signed_by,
        destination=body.destination,
    )
    append_audit(
        db,
        settings.audit_hmac_key,
        event_type="report_archived",
        user_id=body.signed_by,
        patient_id=body.patient_id,
        use_case="UC2_REPORT",
        payload={"archive_id": row.id, "destination": row.destination, "report_type": row.report_type},
    )
    return ArchiveReportResponse(
        archive_id=row.id,
        destination=row.destination,
        archive_path=row.archive_path,
    )


@router.get("/archive/{archive_id}")
async def get_archive(
    archive_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(ReportArchive, archive_id)
    if not row:
        return {"found": False}
    return {
        "found": True,
        "archive_id": row.id,
        "created_at": row.created_at,
        "report_type": row.report_type,
        "destination": row.destination,
        "archive_path": row.archive_path,
        "signed_by": row.signed_by,
    }
