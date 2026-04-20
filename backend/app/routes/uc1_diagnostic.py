from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dispatcher import LLMDispatcher
from app.db import get_db
from app.deps import get_dispatcher
from app.models.feedback import Feedback
from app.schemas.diagnostic import (
    DiagnosticRequest,
    DiagnosticResponse,
    ExplainDiagnosticRequest,
    ExplainDiagnosticResponse,
    FeedbackRequest,
)
from app.services.diagnostic_service import run_diagnostic, run_diagnostic_explain

router = APIRouter(prefix="/api/uc1", tags=["UC1-diagnostic"])


@router.post("/diagnose", response_model=DiagnosticResponse)
async def diagnose(
    body: DiagnosticRequest,
    db: Session = Depends(get_db),
    dispatcher: LLMDispatcher = Depends(get_dispatcher),
):
    return await run_diagnostic(db, dispatcher, body)


@router.post("/feedback")
async def feedback(body: FeedbackRequest, db: Session = Depends(get_db)):
    row = Feedback(
        user_id=body.user_id,
        use_case=body.use_case,
        audit_log_id=body.audit_log_id,
        action=body.action,
        note=body.note,
        context=body.context,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "recorded": True}


@router.post("/explain", response_model=ExplainDiagnosticResponse)
async def explain_differential(
    body: ExplainDiagnosticRequest,
    db: Session = Depends(get_db),
    dispatcher: LLMDispatcher = Depends(get_dispatcher),
):
    return await run_diagnostic_explain(db, dispatcher, body)
