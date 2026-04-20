from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.dispatcher import LLMDispatcher
from app.core.router import UseCase
from app.schemas.qa import QARequest, QAResponse


SYSTEM_PROMPT = (
    "You are a medical Q&A assistant.\n"
    "Answer only from the provided context snippets.\n"
    "If the answer is not present in context, say exactly: "
    "'I could not find this in the indexed medical_qa dataset.'\n"
    "Keep answers short and practical (2-6 sentences)."
)


async def run_qa(
    db: Session,
    dispatcher: LLMDispatcher,
    req: QARequest,
) -> QAResponse:
    result = await dispatcher.run(
        db,
        use_case=UseCase.UC_QA,
        query=req.question,
        payload_for_routing=req.question,
        system=SYSTEM_PROMPT,
        user_id=req.user_id,
        metadata={"dataset": "medical_qa.json"},
        use_rag=True,
        max_tokens=320,
        temperature=0.1,
    )
    return QAResponse(
        answer=result.response.text.strip(),
        provider_used=result.provider_used,
        model_used=result.model_used,
        rule=result.rule,
        audit_id=result.audit_id,
        citations=result.citations,
    )

