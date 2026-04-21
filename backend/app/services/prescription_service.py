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
    # AVK / anticoagulants
    "warfarine": "warfarin",
    "coumadine": "warfarin",
    "sintrom": "acenocoumarol",
    "previscan": "fluindione",
    "rivaroxaban": "rivaroxaban",
    "xarelto": "rivaroxaban",
    "apixaban": "apixaban",
    "eliquis": "apixaban",
    "dabigatran": "dabigatran",
    "pradaxa": "dabigatran",
    # Antiagrégants
    "aspirine": "aspirin",
    "acide": "aspirin",  # "acide acétylsalicylique" -> first token
    "kardegic": "aspirin",
    "clopidogrel": "clopidogrel",
    "plavix": "clopidogrel",
    # AINS
    "ibuprofene": "ibuprofen",
    "ibuprofène": "ibuprofen",
    "naproxene": "naproxen",
    "naproxène": "naproxen",
    "diclofenac": "diclofenac",
    "ketoprofene": "ketoprofen",
    # Antibiotiques
    "amoxicilline": "amoxicillin",
    "augmentin": "amoxicillin",
    "clarithromycine": "clarithromycin",
    "érythromycine": "erythromycin",
    "erythromycine": "erythromycin",
    "azithromycine": "azithromycin",
    "ciprofloxacine": "ciprofloxacin",
    "levofloxacine": "levofloxacin",
    "cotrimoxazole": "cotrimoxazole",
    "bactrim": "cotrimoxazole",
    "trimethoprime": "trimethoprim",
    "rifampicine": "rifampicin",
    "gentamicine": "gentamicin",
    "acide_fusidique": "fusidic_acid",
    # Antifongiques
    "miconazole": "miconazole",
    "daktarin": "miconazole",
    "fluconazole": "fluconazole",
    "triflucan": "fluconazole",
    "itraconazole": "itraconazole",
    "ketoconazole": "ketoconazole",
    # Anti-H2 / IPP
    "omeprazole": "omeprazole",
    "mopral": "omeprazole",
    "esomeprazole": "esomeprazole",
    "pantoprazole": "pantoprazole",
    "inipomp": "pantoprazole",
    "rabeprazole": "rabeprazole",
    # Hypoglycémiants
    "metformine": "metformin",
    "glucophage": "metformin",
    "stagid": "metformin",
    # Analgésiques
    "paracétamol": "paracetamol",
    "paracetamol": "paracetamol",
    "doliprane": "paracetamol",
    "dafalgan": "paracetamol",
    "efferalgan": "paracetamol",
    "tramadol": "tramadol",
    "contramal": "tramadol",
    "topalgic": "tramadol",
    "codeine": "codeine",
    "codéine": "codeine",
    "morphine": "morphine",
    "skenan": "morphine",
    "oxycodone": "oxycodone",
    "oxycontin": "oxycodone",
    # Psychotropes
    "fluoxetine": "fluoxetine",
    "prozac": "fluoxetine",
    "sertraline": "sertraline",
    "zoloft": "sertraline",
    "citalopram": "citalopram",
    "seropram": "citalopram",
    "escitalopram": "escitalopram",
    "seroplex": "escitalopram",
    "paroxetine": "paroxetine",
    "deroxat": "paroxetine",
    "moclobemide": "moclobemide",
    "moclamine": "moclobemide",
    "selegiline": "selegiline",
    "millepertuis": "millepertuis",
    "diazepam": "diazepam",
    "valium": "diazepam",
    "alprazolam": "alprazolam",
    "xanax": "alprazolam",
    "oxazepam": "oxazepam",
    "seresta": "oxazepam",
    # CV
    "amiodarone": "amiodarone",
    "cordarone": "amiodarone",
    "verapamil": "verapamil",
    "isoptine": "verapamil",
    "diltiazem": "diltiazem",
    "digoxine": "digoxin",
    "digoxin": "digoxin",
    "amlodipine": "amlodipine",
    "amlor": "amlodipine",
    "ramipril": "ramipril",
    "triatec": "ramipril",
    "enalapril": "enalapril",
    "lisinopril": "lisinopril",
    "captopril": "captopril",
    "losartan": "losartan",
    "cozaar": "losartan",
    "valsartan": "valsartan",
    "irbesartan": "irbesartan",
    "furosemide": "furosemide",
    "lasilix": "furosemide",
    "hydrochlorothiazide": "hydrochlorothiazide",
    "esidrex": "hydrochlorothiazide",
    "spironolactone": "spironolactone",
    "aldactone": "spironolactone",
    "atenolol": "atenolol",
    "tenormine": "atenolol",
    "bisoprolol": "beta_blocker",
    "metoprolol": "beta_blocker",
    "propranolol": "beta_blocker",
    "avlocardyl": "beta_blocker",
    # Statines
    "simvastatine": "simvastatin",
    "zocor": "simvastatin",
    "atorvastatine": "atorvastatin",
    "tahor": "atorvastatin",
    "rosuvastatine": "rosuvastatin",
    "crestor": "rosuvastatin",
    "pravastatine": "pravastatin",
    # Autres
    "methotrexate": "methotrexate",
    "methotrexate_oral": "methotrexate",
    "allopurinol": "allopurinol",
    "zyloric": "allopurinol",
    "azathioprine": "azathioprine",
    "imurel": "azathioprine",
    "mercaptopurine": "mercaptopurine",
    "colchicine": "colchicine",
    "colchimax": "colchicine",
    "lithium": "lithium",
    "teralithe": "lithium",
    "theophylline": "theophylline",
    "clozapine": "clozapine",
    "leponex": "clozapine",
    "phenytoine": "phenytoin",
    "phenytoin": "phenytoin",
    "carbamazepine": "carbamazepine",
    "tegretol": "carbamazepine",
    "tamoxifen": "tamoxifen",
    "tamoxifene": "tamoxifen",
    "cyclosporine": "cyclosporine",
    "neoral": "cyclosporine",
    "sildenafil": "sildenafil",
    "viagra": "sildenafil",
    "tamsulosin": "tamsulosin",
    "omix": "tamsulosin",
    "insuline": "insulin",
    "insulin": "insulin",
    # Abstract groups used in the interaction table
    "quinine": "quinine",
    "hydroxychloroquine": "hydroxychloroquine",
    "plaquenil": "hydroxychloroquine",
    "triptan": "triptans",
    "sumatriptan": "triptans",
    "imigrane": "triptans",
    "zolmitriptan": "triptans",
    "contrast": "contrast_iodine",
    "iode": "contrast_iodine",
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


_AINS = {"ibuprofen", "ibuprofène", "aspirin", "aspirine", "naproxen", "diclofenac", "ketoprofen"}
_QT_PROLONGATEURS = {
    "amiodarone", "citalopram", "escitalopram", "clarithromycin", "azithromycin",
    "erythromycin", "levofloxacin", "ciprofloxacin", "quinine", "hydroxychloroquine",
    "ondansetron", "haloperidol", "methadone", "sotalol",
}
_SEROTONINERGIQUES = {
    "sertraline", "fluoxetine", "citalopram", "escitalopram", "paroxetine",
    "venlafaxine", "moclobemide", "selegiline", "tramadol", "triptans", "millepertuis",
}
_ANTICHOLINERGIQUES = {
    "amitriptyline", "clomipramine", "oxybutynin", "solifenacin", "scopolamine",
    "promethazine", "diphenhydramine", "hydroxyzine",
}


def check_contraindications(patient: PatientProfile, new_meds: list[Medication]) -> list[InteractionAlert]:
    """Encode high-signal contraindications from the HAS thesaurus + ANSM.
    Kept deterministic: rule-based, no LLM involvement. Each rule is a literal,
    documented clinical contraindication.
    """
    alerts: list[InteractionAlert] = []

    for m in new_meds:
        name = _norm(m.name)

        # Renal: metformine
        if name == "metformin" and (patient.dfg_ml_min is not None and patient.dfg_ml_min < 30):
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism=f"DFG {patient.dfg_ml_min} mL/min < 30 — risque d'acidose lactique",
            ))
        # Renal: AINS
        if name in _AINS and (patient.dfg_ml_min is not None and patient.dfg_ml_min < 30):
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism=f"AINS contre-indiqué si DFG < 30 mL/min (ici {patient.dfg_ml_min}) — risque d'insuffisance rénale aiguë",
            ))
        # Renal: digoxine à dose standard
        if name == "digoxin" and (patient.dfg_ml_min is not None and patient.dfg_ml_min < 50):
            alerts.append(InteractionAlert(
                type="contraindication", severity="moderate", drug_a=m.name,
                mechanism=f"Adapter la dose: DFG {patient.dfg_ml_min} mL/min (risque de toxicité digitalique)",
            ))
        # Insuffisance hépatique sévère
        if patient.hepatic_failure and name in {"metformin", "methotrexate", "paracetamol", "statins",
                                                "atorvastatin", "simvastatin", "rosuvastatin",
                                                "amiodarone", "valproate"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Insuffisance hépatique sévère — métabolisme altéré, risque de toxicité",
            ))

        # Grossesse
        if patient.pregnant and name in _AINS:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="AINS contre-indiqué à partir du 2e-3e trimestre (fermeture canal artériel, oligoamnios)",
            ))
        if patient.pregnant and name in {"warfarin", "acenocoumarol", "fluindione"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="AVK tératogène au T1 (embryopathie) et hémorragique au T3",
            ))
        if patient.pregnant and name in {"isotretinoin", "acitretin", "methotrexate",
                                         "ribavirin", "mycophenolate", "thalidomide"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Tératogène majeur — contre-indication absolue en grossesse",
            ))
        if patient.pregnant and name in {"ramipril", "enalapril", "lisinopril", "captopril",
                                         "losartan", "valsartan", "irbesartan"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="IEC/ARA2 contre-indiqué à partir du T2 (oligoamnios, anomalies rénales)",
            ))

        # Asthme + bêta-bloquants non sélectifs
        if patient.asthma and name in {"beta_blocker", "propranolol"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Bêta-bloquant non sélectif contre-indiqué chez l'asthmatique — risque de bronchospasme",
            ))

        # Ulcère gastroduodénal évolutif + AINS
        if patient.peptic_ulcer and name in _AINS:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Ulcère gastroduodénal évolutif — AINS contre-indiqué",
            ))

        # Épilepsie + tramadol / abaisseurs de seuil
        if patient.epilepsy and name in {"tramadol", "bupropion"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Abaisseur du seuil épileptogène chez un patient épileptique",
            ))

        # QT long baseline + prolongateurs QT
        if patient.qt_ms and patient.qt_ms > 450 and name in _QT_PROLONGATEURS:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism=f"QTc {patient.qt_ms:.0f} ms > 450 — prolongateur QT contre-indiqué",
            ))

        # Hyperkaliémie + épargneurs K+
        if patient.kaliemia_mmol and patient.kaliemia_mmol >= 5.5 and name in {
            "spironolactone", "eplerenone", "amiloride", "triamterene",
            "ramipril", "enalapril", "lisinopril", "captopril",
            "losartan", "valsartan", "irbesartan",
        }:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism=f"Kaliémie {patient.kaliemia_mmol:.1f} mmol/L — risque d'hyperkaliémie aggravée",
            ))

        # Pédiatrie
        if patient.age is not None and patient.age < 16 and name in {"aspirin", "aspirine"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Aspirine contre-indiquée avant 16 ans — risque de syndrome de Reye",
            ))
        if patient.age is not None and patient.age < 12 and name in {"codeine", "tramadol"}:
            alerts.append(InteractionAlert(
                type="contraindication", severity="major", drug_a=m.name,
                mechanism="Opioïdes contre-indiqués avant 12 ans (ANSM 2013/2017)",
            ))

    # Triple whammy (IEC ou ARA2) + AINS + diurétique → IRA
    current_tokens = {_norm(c.name) for c in patient.current_medications}
    iec_ara = {"ramipril", "enalapril", "lisinopril", "captopril", "losartan", "valsartan", "irbesartan"}
    diuretics = {"furosemide", "hydrochlorothiazide", "spironolactone", "indapamide"}
    for m in new_meds:
        name = _norm(m.name)
        if name in _AINS:
            has_iec = bool(current_tokens & iec_ara)
            has_diuretic = bool(current_tokens & diuretics)
            if has_iec and has_diuretic:
                alerts.append(InteractionAlert(
                    type="contraindication", severity="major", drug_a=m.name,
                    mechanism="Triple whammy: IEC/ARA2 + diurétique + AINS — risque élevé d'insuffisance rénale aiguë",
                ))

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
