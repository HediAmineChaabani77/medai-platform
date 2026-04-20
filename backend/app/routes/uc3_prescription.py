from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.dispatcher import LLMDispatcher
from app.db import get_db
from app.deps import get_dispatcher
from app.models.drug import Drug, DrugComposition
from app.schemas.prescription import PrescriptionRequest, PrescriptionResponse
from app.services.prescription_service import run_prescription_check

router = APIRouter(prefix="/api/uc3", tags=["UC3-prescription"])


@router.get("/drug-search")
def drug_search(q: str, limit: int = 8, db: Session = Depends(get_db)):
    """Autocomplete over BDPM drugs by commercial name or active substance.
    Returns compact records suitable for a picker dropdown.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return {"results": []}
    ilike = f"%{q}%"

    # Match on drug name OR on any composition substance_name for that CIS.
    subq = (
        db.query(DrugComposition.cis)
        .filter(DrugComposition.substance_name.ilike(ilike))
        .subquery()
    )
    rows = (
        db.query(Drug)
        .filter(or_(Drug.name.ilike(ilike), Drug.cis.in_(subq)))
        .filter(func.coalesce(Drug.commercial_status, "") != "")
        .limit(max(1, min(25, limit)))
        .all()
    )
    out = []
    for d in rows:
        subs = [c.substance_name for c in d.compositions[:3]] if d.compositions else []
        out.append({
            "cis": d.cis, "name": d.name, "form": d.form,
            "routes": (d.routes or "").split(";") if d.routes else [],
            "substances": subs,
        })
    return {"results": out}


@router.post("/check", response_model=PrescriptionResponse)
async def check_prescription(
    body: PrescriptionRequest,
    db: Session = Depends(get_db),
    dispatcher: LLMDispatcher = Depends(get_dispatcher),
):
    resp = await run_prescription_check(db, dispatcher, body)
    if resp.blocked:
        raise HTTPException(status_code=409, detail=resp.model_dump())
    return resp
