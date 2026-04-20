from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.dispatcher import LLMDispatcher
from app.core.router import UseCase
from app.models.drug import Drug, DrugInteraction, GenericGroupEntry
from app.schemas.prescription import (
    InteractionAlert,
    Medication,
    PatientProfile,
    PrescriptionRequest,
    PrescriptionResponse,
    Severity,
)
from app.services.dmp_service import get_patient_from_dmp


SEVERITY_ORDER = {"minor": 1, "moderate": 2, "major": 3}

# French commercial/DCI variants -> canonical DCI used by the interaction table.
# Extend as new sources (DrugBank, Thériaque) are ingested.
DRUG_ALIASES: dict[str, str] = {
    "warfarine": "warfarin",
    "aspirine": "aspirin",
    "acide": "aspirin",  # "acide acétylsalicylique" -> first token
    "ibuprofene": "ibuprofen",
    "ibuprofène": "ibuprofen",
    "amoxicilline": "amoxicillin",
    "paracétamol": "paracetamol",
    "metformine": "metformin",
    "clarithromycine": "clarithromycin",
}


def _norm(name: str) -> str:
    if not name:
        return ""
    token = name.strip().lower().split()[0]
    return DRUG_ALIASES.get(token, token)


def check_allergies(patient: PatientProfile, new_meds: list[Medication]) -> list[InteractionAlert]:
    alerts: list[InteractionAlert] = []
    allergies = [a.strip().lower() for a in patient.allergies]
    for m in new_meds:
        name = _norm(m.name)
        for a in allergies:
            if a and (a in name or name in a):
                alerts.append(
                    InteractionAlert(
                        type="allergy",
                        severity="major",
                        drug_a=m.name,
                        mechanism=f"Allergie documentée à {a}",
                        note="Blocage automatique.",
                    )
                )
    return alerts


def check_contraindications(patient: PatientProfile, new_meds: list[Medication]) -> list[InteractionAlert]:
    alerts: list[InteractionAlert] = []
    for m in new_meds:
        name = _norm(m.name)
        if name == "metformin" and (patient.dfg_ml_min is not None and patient.dfg_ml_min < 30):
            alerts.append(
                InteractionAlert(
                    type="contraindication",
                    severity="major",
                    drug_a=m.name,
                    mechanism=f"DFG {patient.dfg_ml_min} mL/min < 30 — risque d'acidose lactique",
                )
            )
        if name in {"ibuprofen", "ibuprofène", "aspirin", "aspirine"} and patient.pregnant:
            alerts.append(
                InteractionAlert(
                    type="contraindication",
                    severity="major",
                    drug_a=m.name,
                    mechanism="AINS contre-indiqué à partir du 2e-3e trimestre de grossesse",
                )
            )
        if name == "warfarin" and patient.pregnant:
            alerts.append(
                InteractionAlert(
                    type="contraindication",
                    severity="major",
                    drug_a=m.name,
                    mechanism="AVK tératogène au T1 et hémorragique au T3",
                )
            )
    return alerts


def check_redundancy(patient: PatientProfile, new_meds: list[Medication]) -> list[InteractionAlert]:
    alerts: list[InteractionAlert] = []
    current_atcs = [m.atc for m in patient.current_medications if m.atc]
    for m in new_meds:
        if m.atc and m.atc in current_atcs:
            alerts.append(
                InteractionAlert(
                    type="therapeutic_redundancy",
                    severity="moderate",
                    drug_a=m.name,
                    mechanism=f"Même classe ATC ({m.atc}) qu'un traitement en cours",
                )
            )
    return alerts


def check_pairwise_interactions(
    db: Session, patient: PatientProfile, new_meds: list[Medication]
) -> list[InteractionAlert]:
    alerts: list[InteractionAlert] = []
    current_names = [_norm(m.name) for m in patient.current_medications]
    new_names = [_norm(m.name) for m in new_meds]
    # Pairs: new x current, and new x new.
    candidates: list[tuple[str, str]] = []
    for nn in new_names:
        for cn in current_names:
            if nn and cn and nn != cn:
                candidates.append((nn, cn))
    for i, a in enumerate(new_names):
        for b in new_names[i + 1 :]:
            if a and b and a != b:
                candidates.append((a, b))

    for a, b in candidates:
        row = (
            db.query(DrugInteraction)
            .filter(
                or_(
                    (DrugInteraction.drug_a == a) & (DrugInteraction.drug_b == b),
                    (DrugInteraction.drug_a == b) & (DrugInteraction.drug_b == a),
                )
            )
            .first()
        )
        if row:
            alerts.append(
                InteractionAlert(
                    type="interaction",
                    severity=row.severity,
                    drug_a=a,
                    drug_b=b,
                    mechanism=row.mechanism,
                    note=row.note,
                )
            )
    return alerts


def max_severity(alerts: list[InteractionAlert]) -> Severity | None:
    if not alerts:
        return None
    return max((a.severity for a in alerts), key=lambda s: SEVERITY_ORDER[s])


def _alt_is_safe(name: str, substances: list[str], allergen_tokens: set[str]) -> bool:
    """Reject any alternative whose commercial name or active substance contains
    an allergen token. Protects against the amoxicilline-allergy → amoxicilline+clav trap.
    """
    if not allergen_tokens:
        return True
    hay = (name + " " + " ".join(substances or [])).lower()
    return not any(tok in hay for tok in allergen_tokens if tok)


def suggest_alternatives(
    db: Session,
    alerts: list[InteractionAlert],
    new_meds: list[Medication],
    allergens: list[str] | None = None,
) -> list[str]:
    """Suggest alternatives using generic groups as a pragmatic local-only fallback.

    Alternatives are filtered against the patient's documented allergens: any
    candidate whose name or active substance matches an allergen is dropped,
    so an amoxicilline-allergic patient never gets amoxicilline+clav suggested.
    """
    seeds = {(_norm(m.name)) for m in new_meds if m.name}
    for a in alerts:
        if a.drug_a:
            seeds.add(_norm(a.drug_a))
        if a.drug_b:
            seeds.add(_norm(a.drug_b))

    allergen_tokens: set[str] = set()
    for a in (allergens or []):
        tok = _norm(a)
        if tok:
            allergen_tokens.add(tok)
        # Also catch the full phrase without normalisation (e.g., "pénicilline").
        base = (a or "").strip().lower()
        if base:
            allergen_tokens.add(base)

    # Alerts of type=allergy carry the allergen in drug_a — add it as a forbidden token.
    for alert in alerts:
        if alert.type == "allergy" and alert.drug_a:
            allergen_tokens.add(_norm(alert.drug_a))

    suggestions: list[str] = []
    seen: set[str] = set()
    for token in list(seeds)[:6]:
        if not token:
            continue
        drug = db.query(Drug).filter(Drug.name.ilike(f"%{token}%")).first()
        if not drug:
            continue
        group_rows = db.query(GenericGroupEntry).filter(GenericGroupEntry.cis == drug.cis).all()
        group_ids = [g.group_id for g in group_rows if g.group_id]
        if not group_ids:
            continue
        cis_rows = (
            db.query(GenericGroupEntry.cis)
            .filter(GenericGroupEntry.group_id.in_(group_ids), GenericGroupEntry.cis != drug.cis)
            .limit(12)
            .all()
        )
        cises = [r[0] for r in cis_rows]
        if not cises:
            continue
        alt_drugs = db.query(Drug).filter(Drug.cis.in_(cises)).limit(10).all()
        for alt in alt_drugs:
            name = alt.name.strip()
            low = name.lower()
            if low in seen:
                continue
            subs = [c.substance_name for c in (alt.compositions or [])]
            if not _alt_is_safe(name, subs, allergen_tokens):
                continue
            seen.add(low)
            suggestions.append(name)
            if len(suggestions) >= 6:
                return suggestions

    # Safety fallback if no group-based alternative was found. Still honour allergens.
    if not suggestions:
        for fallback in ("Paracétamol", "Amoxicilline", "Metformine"):
            if fallback.lower() in seen:
                continue
            if not _alt_is_safe(fallback, [fallback], allergen_tokens):
                continue
            suggestions.append(fallback)
    return suggestions[:6]


SYSTEM_PROMPT = (
    "Tu es un pharmacologue clinique. Tu expliques au médecin, de façon concise et sourcée, "
    "les alertes de sécurité relatives à une prescription. "
    "N'utilise AUCUNE source externe: base-toi uniquement sur les alertes structurées fournies. "
    "N'invente pas de médicaments ni de références [SRCx]."
)


def _deterministic_explanation(alerts: list[InteractionAlert], blocked: bool) -> str:
    if not alerts:
        return ""
    lines = []
    for a in alerts:
        pair = f"{a.drug_a} + {a.drug_b}" if a.drug_b else a.drug_a
        lines.append(f"- [{a.severity.upper()}] {a.type}: {pair} — {a.mechanism}")
    conclusion = (
        "Conduite à tenir: prescription bloquée (sévérité majeure)."
        if blocked
        else "Conduite à tenir: prescription possible avec précautions et surveillance clinique."
    )
    return "Alertes détectées:\n" + "\n".join(lines) + f"\n\n{conclusion}"


async def run_prescription_check(
    db: Session,
    dispatcher: LLMDispatcher,
    req: PrescriptionRequest,
) -> PrescriptionResponse:
    patient = req.patient.model_copy(deep=True)
    dmp_record = get_patient_from_dmp(req.patient_id, get_settings())
    if dmp_record:
        if patient.age is None and dmp_record.get("age") is not None:
            patient.age = int(dmp_record.get("age"))
        if not patient.sex and dmp_record.get("sexe"):
            patient.sex = str(dmp_record.get("sexe"))
        if not patient.allergies and isinstance(dmp_record.get("allergies"), list):
            patient.allergies = [str(x) for x in dmp_record.get("allergies") if str(x).strip()]
        if patient.dfg_ml_min is None and dmp_record.get("dfg_ml_min") is not None:
            patient.dfg_ml_min = float(dmp_record.get("dfg_ml_min"))
        if not patient.current_medications and isinstance(dmp_record.get("current_medications"), list):
            meds: list[Medication] = []
            for row in dmp_record.get("current_medications"):
                if isinstance(row, dict) and row.get("name"):
                    meds.append(Medication(**row))
            patient.current_medications = meds
        if not patient.pregnant and bool(dmp_record.get("pregnant")):
            patient.pregnant = True

    alerts: list[InteractionAlert] = []
    alerts += check_allergies(patient, req.new_medications)
    alerts += check_contraindications(patient, req.new_medications)
    alerts += check_redundancy(patient, req.new_medications)
    alerts += check_pairwise_interactions(db, patient, req.new_medications)

    severity = max_severity(alerts)
    blocked = severity == "major"
    alternatives = suggest_alternatives(db, alerts, req.new_medications, allergens=patient.allergies) if alerts else []

    explanation = _deterministic_explanation(alerts, blocked)
    provider_used = model_used = rule = None
    audit_id = None
    citations: list[dict] = []

    if alerts:
        names = [m.name for m in req.new_medications]
        current = [m.name for m in patient.current_medications]
        bullet = "\n".join(
            f"- [{a.severity.upper()}] {a.type}: {a.drug_a}"
            + (f" + {a.drug_b}" if a.drug_b else "")
            + f" — {a.mechanism}"
            for a in alerts
        )
        query = (
            f"Nouvelle prescription: {names}.\n"
            f"Traitements en cours: {current}.\n"
            f"Alertes détectées:\n{bullet}\n\n"
            "Rédige une explication concise (<= 200 mots) à destination d'un médecin. "
            "Utilise uniquement ces alertes, sans source externe, et conclus sur la conduite à tenir."
        )
        try:
            result = await dispatcher.run(
                db,
                use_case=UseCase.UC3_PRESCRIPTION,
                query=query,
                payload_for_routing=" ".join(names + current),
                system=SYSTEM_PROMPT,
                user_id=req.physician_id,
                patient_id=req.patient_id,
                metadata={"department": req.department, "alert_count": len(alerts), "max_severity": severity},
                use_rag=False,
                max_tokens=280,
                temperature=0.1,
                extra_audit={"blocked": blocked, "alerts": [a.model_dump() for a in alerts]},
            )
            if result.response.text.strip():
                explanation = result.response.text
            provider_used = result.provider_used
            model_used = result.model_used
            rule = result.rule
            audit_id = result.audit_id
            citations = result.citations
        except Exception:
            # Safety-first fallback: interaction blocking must remain available even if LLM generation fails.
            pass

    return PrescriptionResponse(
        blocked=blocked,
        max_severity=severity,
        alerts=alerts,
        explanation=explanation,
        provider_used=provider_used,
        model_used=model_used,
        rule=rule,
        audit_id=audit_id,
        alternatives=alternatives,
        citations=citations,
    )
