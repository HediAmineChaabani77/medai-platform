from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dispatcher import LLMDispatcher
from app.db import get_db
from app.deps import get_dispatcher
from app.schemas.qa import QARequest, QAResponse
from app.services.qa_service import run_qa

router = APIRouter(prefix="/api/qa", tags=["QA"])


@router.post("/ask", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    db: Session = Depends(get_db),
    dispatcher: LLMDispatcher = Depends(get_dispatcher),
):
    return await run_qa(db, dispatcher, body)

