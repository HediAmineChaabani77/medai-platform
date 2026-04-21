from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.dispatcher import LLMDispatcher
from app.core.router import UseCase
from app.schemas.diagnostic import (
    DiagnosticCandidate,
    DiagnosticRequest,
    DiagnosticResponse,
    ExplainDiagnosticRequest,
    ExplainDiagnosticResponse,
)
from app.services.dmp_service import get_patient_from_dmp, merge_uc1_context


SYSTEM_PROMPT = (
    "Tu es un assistant de raisonnement diagnostique pour médecin. "
    "Tu proposes un diagnostic différentiel clinique (2 à 4 hypothèses), ordonné par probabilité. "
    "Chaque hypothèse doit être une maladie/syndrome (jamais médicament, posologie, examen, symptôme isolé). "
    "N'invente aucune donnée clinique absente. "
    "Mets en avant les causes graves à exclure en urgence quand les symptômes l'imposent. "
    "N'inclus jamais de conduite thérapeutique."
)

RESPONSE_INSTRUCTIONS = (
    "Réponds STRICTEMENT en JSON avec ce schéma exact:\n"
    '{"diagnoses":[{"condition":"nom de la pathologie","probability":0.0,"reasoning":"explication clinique","icd10":"code CIM-10 ou null","citations":["SRC1"]}],"red_flags":["signal d urgence"]}\n\n'
    "Contraintes: 2 à 4 diagnostics, probabilités entre 0 et 1, ordre décroissant de probabilité, "
    "somme des probabilités proche de 1. "
    "Les 'condition' doivent être des pathologies cliniques (ex: 'Syndrome coronarien aigu', 'Embolie pulmonaire'), "
    "jamais des noms de médicaments ni des classes thérapeutiques. "
    "Mets citations=[] si aucune source n'est utilisée. "
    "Les 'red_flags' doivent être des signaux d'alarme cliniques précis (pas de placeholders génériques). "
    "Aucun texte avant ou après le JSON."
)

DIAGNOSTIC_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnoses": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "condition": {"type": "string"},
                    "probability": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "icd10": {"type": ["string", "null"]},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["condition", "probability", "reasoning", "icd10", "citations"],
                "additionalProperties": False,
            },
        },
        "red_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": ["diagnoses", "red_flags"],
    "additionalProperties": False,
}

_GENERIC_RED_FLAGS = {
    "signal d urgence",
    "signal d'urgence",
    "urgence",
    "drapeau rouge",
    "red flag",
}
_RED_FLAG_NORMALIZATION = {
    "désespoir respiratoire": "Détresse respiratoire",
    "desespoir respiratoire": "Détresse respiratoire",
    "insuffisance respiratoire aigue": "Insuffisance respiratoire aiguë",
    "cardiac arrest imminent": "Risque d'arrêt cardiaque imminent",
    "respiratory failure imminent": "Insuffisance respiratoire aiguë",
}
_CONDITION_NORMALIZATION = {
    "pleurisy": "Pleurésie",
    "myocardite acuté": "Myocardite aiguë",
    "pneumonie aigué": "Pneumonie aiguë",
    "proctologie": "Pathologie anorectale aiguë",
}

_MEDICATION_NAME_HINTS = {
    "warfarin",
    "aspirin",
    "amoxicilline",
    "metformine",
    "ibuprofene",
    "ibuprofène",
    "paracetamol",
    "paracétamol",
}
_MEDICATION_SUFFIXES = (
    "mab",
    "pril",
    "sartan",
    "xaban",
    "statine",
    "azole",
    "olol",
    "cillin",
    "mycine",
    "caine",
    "prazole",
)
_DOSAGE_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|ml|mcg|µg|ui|iu)\b", flags=re.IGNORECASE)


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _normal_condition_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _looks_like_medication(condition: str) -> bool:
    low = (condition or "").lower()
    if not low:
        return True
    if low in _MEDICATION_NAME_HINTS:
        return True
    if _DOSAGE_PATTERN.search(low):
        return True
    if condition.isupper() and len(condition) >= 5:
        return True
    for suffix in _MEDICATION_SUFFIXES:
        if low.endswith(suffix) and len(low.split()) == 1:
            return True
    return False


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    txt = text.lower()
    return any(n in txt for n in needles)


def _heuristic_differential(symptoms: str, patient_context: dict | None = None) -> tuple[list[dict], list[str]]:
    s = (symptoms or "").lower()
    patient_context = patient_context or {}
    sex = str(patient_context.get("sexe") or patient_context.get("sex") or "").strip().lower()

    # Shared predicates reused by multiple branches.
    fever_positive = (
        _contains_any(s, ("fièvre", "fievre", "fébrile", "febrile"))
        and not _contains_any(s, ("sans fièvre", "sans fievre", "afébrile", "apyrétique"))
    )

    if _contains_any(s, ("douleur thorac", "thoracique", "oppression", "irradiation bras", "poitrine")):
        return (
            [
                {
                    "condition": "Syndrome coronarien aigu",
                    "probability": 0.46,
                    "reasoning": "Douleur thoracique constrictive/irradiée et terrain cardiovasculaire compatible.",
                    "icd10": "I20-I24",
                    "citations": [],
                },
                {
                    "condition": "Embolie pulmonaire",
                    "probability": 0.24,
                    "reasoning": "Dyspnée et douleur thoracique aiguë imposent d'éliminer une cause thromboembolique.",
                    "icd10": "I26",
                    "citations": [],
                },
                {
                    "condition": "Dissection aortique",
                    "probability": 0.15,
                    "reasoning": "Diagnostic grave à exclure devant douleur thoracique aiguë intense.",
                    "icd10": "I71.0",
                    "citations": [],
                },
                {
                    "condition": "Péricardite aiguë",
                    "probability": 0.15,
                    "reasoning": "Peut donner douleur thoracique et gêne respiratoire selon le contexte clinique.",
                    "icd10": "I30",
                    "citations": [],
                },
            ],
            [
                "Douleur thoracique persistante > 20 minutes",
                "Dyspnée aiguë ou désaturation",
                "Hypotension, syncope ou altération hémodynamique",
            ],
        )

    if fever_positive and _contains_any(s, ("toux", "dyspn", "essouff")):
        return (
            [
                {
                    "condition": "Pneumonie communautaire",
                    "probability": 0.45,
                    "reasoning": "Association fièvre + toux + atteinte respiratoire compatible avec une infection pulmonaire.",
                    "icd10": "J18",
                    "citations": [],
                },
                {
                    "condition": "Infection virale respiratoire (grippe/COVID-19)",
                    "probability": 0.35,
                    "reasoning": "Tableau pseudo-grippal fréquent avec fièvre, toux et asthénie.",
                    "icd10": "J06",
                    "citations": [],
                },
                {
                    "condition": "Bronchite aiguë",
                    "probability": 0.20,
                    "reasoning": "Toux aiguë fébrile possible sans signe de gravité immédiat.",
                    "icd10": "J20",
                    "citations": [],
                },
            ],
            [
                "Détresse respiratoire",
                "SpO2 < 92%",
                "Hypotension ou confusion",
            ],
        )

    if _contains_any(s, ("dysurie", "brulure miction", "brûlure miction", "pollakiurie")):
        if sex in {"f", "femme", "female"}:
            return (
                [
                    {
                        "condition": "Cystite aiguë simple",
                        "probability": 0.60,
                        "reasoning": "Dysurie/pollakiurie et douleur sus-pubienne sans fièvre évocatrices de cystite.",
                        "icd10": "N30",
                        "citations": [],
                    },
                    {
                        "condition": "Pyélonéphrite aiguë",
                        "probability": 0.22,
                        "reasoning": "À évoquer si apparition de fièvre, frissons ou douleur lombaire.",
                        "icd10": "N10",
                        "citations": [],
                    },
                    {
                        "condition": "Urétrite",
                        "probability": 0.18,
                        "reasoning": "Diagnostic différentiel d'une dysurie selon le contexte infectieux associé.",
                        "icd10": "N34",
                        "citations": [],
                    },
                ],
                [
                    "Fièvre > 38.5°C",
                    "Douleur lombaire/frissons",
                    "Vomissements ou signes de sepsis",
                ],
            )
        return (
            [
                {
                    "condition": "Cystite aiguë simple",
                    "probability": 0.50,
                    "reasoning": "Dysurie/pollakiurie compatibles avec une infection urinaire basse.",
                    "icd10": "N30",
                    "citations": [],
                },
                {
                    "condition": "Prostatite aiguë",
                    "probability": 0.30,
                    "reasoning": "Chez l'homme, douleur pelvienne et troubles urinaires doivent faire évoquer une prostatite.",
                    "icd10": "N41.0",
                    "citations": [],
                },
                {
                    "condition": "Pyélonéphrite aiguë",
                    "probability": 0.20,
                    "reasoning": "À éliminer si fièvre, frissons ou douleur lombaire apparaissent.",
                    "icd10": "N10",
                    "citations": [],
                },
            ],
            [
                "Fièvre > 38.5°C",
                "Douleur lombaire/frissons",
                "Vomissements ou signes de sepsis",
            ],
        )

    if _contains_any(s, ("hémipar", "hemipar", "aphasie", "trouble neurolog", "déviation buccale", "deviation buccale")):
        return (
            [
                {
                    "condition": "AVC ischémique",
                    "probability": 0.55,
                    "reasoning": "Déficit neurologique focal aigu très évocateur d'ischémie cérébrale.",
                    "icd10": "I63",
                    "citations": [],
                },
                {
                    "condition": "Accident ischémique transitoire",
                    "probability": 0.25,
                    "reasoning": "Déficit focal transitoire possible sans lésion constituée persistante.",
                    "icd10": "G45",
                    "citations": [],
                },
                {
                    "condition": "Hypoglycémie symptomatique",
                    "probability": 0.20,
                    "reasoning": "Cause métabolique à exclure devant symptômes neurologiques aigus.",
                    "icd10": "E16.2",
                    "citations": [],
                },
            ],
            [
                "Heure de début des symptômes < 4h30",
                "Altération de conscience",
                "Déficit neurologique progressif",
            ],
        )

    # --- Abdominal pain ---
    if _contains_any(s, ("douleur abdomin", "abdomen", "fosse iliaque", "épigastr", "epigastr",
                         "hypochondre", "mac burney", "defense abdomin", "défense abdomin")):
        return (
            [
                {"condition": "Appendicite aiguë", "probability": 0.35,
                 "reasoning": "Douleur en FID avec défense suggère une appendicite à éliminer.",
                 "icd10": "K35", "citations": []},
                {"condition": "Cholécystite aiguë", "probability": 0.20,
                 "reasoning": "Douleur hypochondre droit / Murphy positif évoquent une cholécystite.",
                 "icd10": "K81", "citations": []},
                {"condition": "Pancréatite aiguë", "probability": 0.15,
                 "reasoning": "Douleur épigastrique transfixiante avec vomissements possible.",
                 "icd10": "K85", "citations": []},
                {"condition": "Occlusion intestinale", "probability": 0.15,
                 "reasoning": "Douleur abdominale + arrêt matière/gaz et vomissements à évaluer.",
                 "icd10": "K56", "citations": []},
                {"condition": "Diverticulite sigmoïdienne", "probability": 0.15,
                 "reasoning": "Douleur FIG avec fièvre classique chez le patient âgé.",
                 "icd10": "K57", "citations": []},
            ],
            [
                "Défense ou contracture abdominale",
                "Instabilité hémodynamique / sepsis",
                "Vomissements bilieux, arrêt total des matières et gaz",
            ],
        )

    # --- Headache ---
    if _contains_any(s, ("céphal", "cephal", "mal de tête", "mal de tete", "migraine")):
        severe = _contains_any(s, ("coup de tonnerre", "brutale", "thunderclap", "la pire de ma vie"))
        return (
            [
                {"condition": "Hémorragie méningée" if severe else "Migraine",
                 "probability": 0.45 if severe else 0.40,
                 "reasoning": "Céphalée en coup de tonnerre à exclure en priorité." if severe
                              else "Céphalée pulsatile unilatérale avec photophobie évoque une migraine.",
                 "icd10": "I60" if severe else "G43", "citations": []},
                {"condition": "Méningite",
                 "probability": 0.25,
                 "reasoning": "Céphalée + fièvre + raideur de nuque à éliminer systématiquement.",
                 "icd10": "G03", "citations": []},
                {"condition": "Hypertension intracrânienne / processus expansif",
                 "probability": 0.15,
                 "reasoning": "Céphalée matinale, vomissements, signes neuro focaux.",
                 "icd10": "G93.2", "citations": []},
                {"condition": "Céphalée de tension",
                 "probability": 0.15,
                 "reasoning": "Céphalée bilatérale en étau sans signe d'alarme.",
                 "icd10": "G44.2", "citations": []},
            ],
            [
                "Céphalée brutale « coup de tonnerre »",
                "Fièvre + raideur de nuque",
                "Déficit neurologique focal ou altération de conscience",
            ],
        )

    # --- Acute dyspnea without fever/cough (so distinct from pneumonia branch) ---
    cough_positive = (
        _contains_any(s, ("toux",))
        and not _contains_any(s, ("sans toux", "ni toux", "pas de toux", "pas toux"))
    )
    if _contains_any(s, ("dyspn", "essouff", "souffle court", "orthopn")) \
       and not fever_positive \
       and not cough_positive:
        return (
            [
                {"condition": "Insuffisance cardiaque décompensée", "probability": 0.35,
                 "reasoning": "Dyspnée + orthopnée évocatrice d'OAP chez le cardiopathe.",
                 "icd10": "I50", "citations": []},
                {"condition": "Embolie pulmonaire", "probability": 0.30,
                 "reasoning": "Dyspnée aiguë isolée avec ou sans douleur thoracique à écarter.",
                 "icd10": "I26", "citations": []},
                {"condition": "Exacerbation d'asthme / BPCO", "probability": 0.20,
                 "reasoning": "Antécédents respiratoires + sibilants + freinage expiratoire.",
                 "icd10": "J45", "citations": []},
                {"condition": "Pneumothorax spontané", "probability": 0.15,
                 "reasoning": "Dyspnée brutale avec douleur latéralisée chez le sujet jeune maigre.",
                 "icd10": "J93", "citations": []},
            ],
            [
                "SpO2 < 92% en air ambiant",
                "Tirage, cyanose, épuisement respiratoire",
                "Hypotension, sueurs, altération de conscience",
            ],
        )

    # --- Fever without respiratory or urinary focus (sepsis differential) ---
    if _contains_any(s, ("fièvre", "fievre", "température 39", "temperature 39", "frissons")) \
       and not _contains_any(s, ("toux", "dyspn", "dysurie", "brulure miction", "brûlure miction")):
        return (
            [
                {"condition": "Sepsis / bactériémie", "probability": 0.30,
                 "reasoning": "Fièvre + frissons imposent d'éliminer un foyer infectieux profond.",
                 "icd10": "A41", "citations": []},
                {"condition": "Pyélonéphrite aiguë", "probability": 0.20,
                 "reasoning": "Fièvre isolée peut être le premier signe d'une PNA à bas bruit.",
                 "icd10": "N10", "citations": []},
                {"condition": "Endocardite infectieuse", "probability": 0.15,
                 "reasoning": "Fièvre prolongée + souffle cardiaque récent = suspicion.",
                 "icd10": "I33", "citations": []},
                {"condition": "Infection virale systémique", "probability": 0.20,
                 "reasoning": "Syndrome pseudo-grippal avec asthénie et myalgies.",
                 "icd10": "B34", "citations": []},
                {"condition": "Paludisme (retour de zone d'endémie)", "probability": 0.15,
                 "reasoning": "Évoquer systématiquement si séjour récent en zone impaludée.",
                 "icd10": "B54", "citations": []},
            ],
            [
                "Hypotension ou altération hémodynamique",
                "Trouble de la conscience",
                "Marbrures, extrémités froides",
            ],
        )

    # --- Isolated weakness / syncope ---
    if _contains_any(s, ("syncope", "malaise", "perte de connaissance", "pc vagale", "p.c.", "lipothymie")):
        return (
            [
                {"condition": "Syncope vagale", "probability": 0.35,
                 "reasoning": "Prodromes vagaux, contexte déclencheur, récupération rapide.",
                 "icd10": "R55", "citations": []},
                {"condition": "Trouble du rythme (FA, BAV, TV)", "probability": 0.25,
                 "reasoning": "Syncope à l'effort ou sans prodrome — ECG indispensable.",
                 "icd10": "I47-I49", "citations": []},
                {"condition": "Hypotension orthostatique", "probability": 0.15,
                 "reasoning": "Chute de PA au passage debout, fréquent sous anti-HTA.",
                 "icd10": "I95.1", "citations": []},
                {"condition": "Embolie pulmonaire", "probability": 0.10,
                 "reasoning": "Peut se révéler par une syncope isolée.",
                 "icd10": "I26", "citations": []},
                {"condition": "Hypoglycémie", "probability": 0.15,
                 "reasoning": "À éliminer systématiquement chez le diabétique traité.",
                 "icd10": "E16.2", "citations": []},
            ],
            [
                "Syncope à l'effort ou précédée de palpitations",
                "Antécédents de mort subite familiale",
                "ECG anormal (BAV, QT long, bloc, WPW)",
            ],
        )

    return ([], [])


def _extract_json(text: str) -> dict:
    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fallback: first balanced {...} block
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"diagnoses": [], "red_flags": [], "_parse_error": True, "_raw": text[:500]}


def _iter_candidate_nodes(node: Any):
    if isinstance(node, dict):
        if any(k in node for k in ("condition", "diagnosis", "name")):
            yield node
        for key in ("diagnoses", "items", "candidates"):
            child = node.get(key)
            if child is not None:
                yield from _iter_candidate_nodes(child)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_candidate_nodes(item)


def _extract_candidates_from_raw(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'"(?:condition|diagnosis|name)"\s*:\s*"([^"]+)"', text):
        condition = m.group(1).strip()
        if not condition:
            continue
        key = condition.lower()
        if key in seen:
            continue
        seen.add(key)

        window = text[m.start() : m.start() + 2000]
        prob_m = re.search(r'"probability"\s*:\s*([-+]?\d+(?:\.\d+)?)', window)
        reasoning_m = re.search(r'"reasoning"\s*:\s*"([^"]*)"', window, flags=re.DOTALL)
        icd_m = re.search(r'"icd10"\s*:\s*(?:"([^"]*)"|null)', window)
        citations_m = re.search(r'"citations"\s*:\s*\[([^\]]*)\]', window, flags=re.DOTALL)

        citations: list[str] = []
        if citations_m:
            citations = [c.strip() for c in re.findall(r'"([^"]+)"', citations_m.group(1))]

        out.append(
            {
                "condition": condition,
                "probability": float(prob_m.group(1)) if prob_m else 0.0,
                "reasoning": (reasoning_m.group(1) if reasoning_m else "").strip(),
                "icd10": (icd_m.group(1).strip() if icd_m and icd_m.group(1) else None),
                "citations": citations,
            }
        )
    return out


def _extract_red_flags_from_raw(text: str) -> list[str]:
    m = re.search(r'"red_flags"\s*:\s*\[([^\]]*)\]', text, flags=re.DOTALL)
    if not m:
        return []
    return [x.strip() for x in re.findall(r'"([^"]+)"', m.group(1))]


def _coerce_candidate(node: dict) -> dict | None:
    if not isinstance(node, dict):
        return None
    condition = _normalize_spaces(str(node.get("condition") or node.get("diagnosis") or node.get("name") or ""))
    condition = _CONDITION_NORMALIZATION.get(condition.lower(), condition)
    if not condition or _looks_like_medication(condition):
        return None
    try:
        probability = float(node.get("probability", 0.0))
    except Exception:
        probability = 0.0
    probability = max(0.0, min(1.0, probability))
    reasoning = _normalize_spaces(str(node.get("reasoning", "")))
    if not reasoning:
        reasoning = "Hypothèse basée sur la cohérence entre symptômes, chronologie et facteurs de risque."
    icd10_raw = node.get("icd10")
    icd10 = None if icd10_raw in (None, "", "null") else _normalize_spaces(str(icd10_raw))
    citations = [str(c).strip() for c in (node.get("citations") or []) if str(c).strip()]
    return {
        "condition": condition,
        "probability": probability,
        "reasoning": reasoning,
        "icd10": icd10,
        "citations": citations,
    }


def _condition_overlap_score(cleaned: list[dict], expected: list[dict]) -> float:
    if not cleaned or not expected:
        return 0.0
    cleaned_keys = [_normal_condition_key(x["condition"]) for x in cleaned]
    hits = 0
    for e in expected:
        ek = _normal_condition_key(e["condition"])
        if not ek:
            continue
        if any((ek in ck) or (ck in ek) for ck in cleaned_keys):
            hits += 1
    return hits / max(1, len(expected))


def _filter_context_incompatible(cleaned: list[dict], patient_context: dict | None) -> list[dict]:
    patient_context = patient_context or {}
    sex = str(patient_context.get("sexe") or patient_context.get("sex") or "").strip().lower()
    out: list[dict] = []
    for row in cleaned:
        name = row["condition"].lower()
        if sex in {"f", "femme", "female"} and "prostat" in name:
            continue
        out.append(row)
    return out


def _match_expected_probability(condition_key: str, expected_prob: dict[str, float]) -> float | None:
    if condition_key in expected_prob:
        return expected_prob[condition_key]
    for ek, value in expected_prob.items():
        if condition_key and ek and ((condition_key in ek) or (ek in condition_key)):
            return value
    return None


def _finalize_candidates(
    candidate_nodes: list[dict],
    *,
    symptoms: str,
    patient_context: dict,
    valid_citation_ids: set[str],
) -> tuple[list[DiagnosticCandidate], list[str]]:
    cleaned: list[dict] = []
    seen: set[str] = set()
    for node in candidate_nodes:
        c = _coerce_candidate(node)
        if not c:
            continue
        key = _normal_condition_key(c["condition"])
        if not key or key in seen:
            continue
        seen.add(key)
        if valid_citation_ids:
            c["citations"] = [x for x in c["citations"] if x in valid_citation_ids]
        else:
            c["citations"] = []
        cleaned.append(c)

    heuristic_dx, heuristic_flags = _heuristic_differential(symptoms, patient_context)
    alignment = _condition_overlap_score(cleaned, heuristic_dx)
    if heuristic_dx and (len(cleaned) < 2 or alignment < 0.34):
        cleaned = list(heuristic_dx)
        seen = {_normal_condition_key(x["condition"]) for x in cleaned}
    elif len(cleaned) < 2:
        for h in heuristic_dx:
            key = _normal_condition_key(h["condition"])
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(h)
            if len(cleaned) >= 4:
                break

    if not cleaned:
        cleaned = [
            {
                "condition": "Infection virale non compliquée",
                "probability": 0.55,
                "reasoning": "Tableau compatible avec une cause infectieuse fréquente en l'absence de signe focal majeur.",
                "icd10": "B34",
                "citations": [],
            },
            {
                "condition": "Infection bactérienne localisée",
                "probability": 0.30,
                "reasoning": "Hypothèse à discuter selon l'évolution clinique et les biomarqueurs.",
                "icd10": "A49",
                "citations": [],
            },
            {
                "condition": "Cause inflammatoire non infectieuse",
                "probability": 0.15,
                "reasoning": "Différentiel alternatif si bilan infectieux initial non contributif.",
                "icd10": None,
                "citations": [],
            },
        ]

    cleaned = _filter_context_incompatible(cleaned, patient_context)
    cleaned = cleaned[:4]
    if heuristic_dx and cleaned:
        expected_prob = {_normal_condition_key(x["condition"]): float(x["probability"]) for x in heuristic_dx}
        matched = 0
        for row in cleaned:
            key = _normal_condition_key(row["condition"])
            mapped = _match_expected_probability(key, expected_prob)
            if mapped is not None:
                row["probability"] = mapped
                matched += 1
            else:
                row["probability"] = min(0.10, float(row.get("probability", 0.0)))
        # If model already found at least one expected condition, keep heuristic ranking priors.
        if matched == 0:
            for row in cleaned:
                row["probability"] = float(row.get("probability", 0.0))
    total = sum(max(0.0, float(x.get("probability", 0.0))) for x in cleaned)
    if total <= 0:
        base = [0.55, 0.30, 0.15, 0.10]
        for i, row in enumerate(cleaned):
            row["probability"] = base[i] if i < len(base) else 0.05
    else:
        for row in cleaned:
            row["probability"] = round(max(0.0, float(row["probability"])) / total, 4)

    cleaned.sort(key=lambda x: x["probability"], reverse=True)
    diagnoses = [
        DiagnosticCandidate(
            condition=row["condition"],
            probability=float(row["probability"]),
            reasoning=row["reasoning"],
            icd10=row.get("icd10"),
            citations=row.get("citations", []),
        )
        for row in cleaned
    ]
    return diagnoses, heuristic_flags


def _finalize_red_flags(red_flag_nodes: list[str], heuristic_flags: list[str]) -> list[str]:
    def _normalize_one(raw: str) -> str:
        text = _normalize_spaces(str(raw))
        if not text:
            return ""
        if text.lower().startswith("signal d'urgence"):
            parts = text.split(":", 1)
            text = _normalize_spaces(parts[1] if len(parts) == 2 else "")
            if not text:
                return ""
        text = _RED_FLAG_NORMALIZATION.get(text.lower(), text)
        if text.lower() in _GENERIC_RED_FLAGS:
            return ""
        return text

    def _is_actionable(text: str) -> bool:
        low = text.lower()
        keywords = (
            "dyspn",
            "désaturation",
            "desaturation",
            "spo2",
            "hypotension",
            "syncope",
            "sepsis",
            "hémodynam",
            "hemodynam",
            "conscience",
            "déficit",
            "deficit",
            "hémipar",
            "hemipar",
            "trouble de la parole",
            "fièvre",
            "fievre",
            "lombaire",
            "saignement",
            "hémorrag",
            "hemorrag",
            "arrêt cardiaque",
            "insuffisance respiratoire",
            "douleur thoracique",
        )
        return any(k in low for k in keywords)

    model_flags = [f for f in (_normalize_one(x) for x in red_flag_nodes) if f]
    if heuristic_flags:
        actionable = [f for f in model_flags if _is_actionable(f)]
        ratio = (len(actionable) / len(model_flags)) if model_flags else 0.0
        source = heuristic_flags if len(model_flags) < 2 or ratio < 0.5 else model_flags
    else:
        source = model_flags

    out: list[str] = []
    seen: set[str] = set()
    for raw in source:
        text = _normalize_one(raw)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= 8:
            break
    return out


async def run_diagnostic(
    db: Session,
    dispatcher: LLMDispatcher,
    req: DiagnosticRequest,
) -> DiagnosticResponse:
    dmp_record = get_patient_from_dmp(req.patient_id, get_settings())
    merged_context = merge_uc1_context(req.patient_context, dmp_record)
    context_summary = json.dumps(merged_context, ensure_ascii=False)
    query = (
        f"Symptômes: {req.symptoms}\n"
        f"Contexte patient (DMP): {context_summary}\n\n"
        f"{RESPONSE_INSTRUCTIONS}"
    )

    result = await dispatcher.run(
        db,
        use_case=UseCase.UC1_DIAGNOSTIC,
        query=query,
        payload_for_routing=req.symptoms + " " + context_summary,
        system=SYSTEM_PROMPT,
        user_id=req.physician_id,
        patient_id=req.patient_id,
        metadata={"department": req.department, "dataset": "medical_qa.json"},
        patient_context=merged_context,
        # UC1 remains primarily model-knowledge based; QA corpus is optimized for QA endpoint.
        use_rag=False,
        max_tokens=800,
        temperature=0.0,
        format=DIAGNOSTIC_JSON_SCHEMA,
    )

    parsed = _extract_json(result.response.text)
    valid_citation_ids = {
        str(c.get("id"))
        for c in result.citations
        if isinstance(c, dict) and c.get("id") is not None
    }
    candidate_nodes = list(_iter_candidate_nodes(parsed.get("diagnoses", []) or []))
    if not candidate_nodes:
        candidate_nodes = _extract_candidates_from_raw(result.response.text)
    diagnoses, heuristic_flags = _finalize_candidates(
        candidate_nodes,
        symptoms=req.symptoms,
        patient_context=merged_context,
        valid_citation_ids=valid_citation_ids,
    )

    red_flag_nodes = parsed.get("red_flags", []) or []
    if not red_flag_nodes:
        red_flag_nodes = _extract_red_flags_from_raw(result.response.text)
    red_flags = _finalize_red_flags(red_flag_nodes, heuristic_flags)

    return DiagnosticResponse(
        diagnoses=diagnoses,
        red_flags=red_flags,
        provider_used=result.provider_used,
        model_used=result.model_used,
        rule=result.rule,
        audit_id=result.audit_id,
        citations=result.citations,
        raw_answer=result.response.text,
    )


async def run_diagnostic_explain(
    db: Session,
    dispatcher: LLMDispatcher,
    req: ExplainDiagnosticRequest,
) -> ExplainDiagnosticResponse:
    dmp_record = get_patient_from_dmp(req.patient_id, get_settings())
    merged_context = merge_uc1_context(req.patient_context, dmp_record)
    context_summary = json.dumps(merged_context, ensure_ascii=False)
    query = (
        f"Symptômes: {req.symptoms}\n"
        f"Contexte patient (DMP): {context_summary}\n"
        f"Comparer les deux hypothèses suivantes:\n"
        f"- Option A: {req.option_a}\n"
        f"- Option B: {req.option_b}\n\n"
        "Réponds en français clinique, concis (6-10 phrases), en expliquant: "
        "1) éléments en faveur de A, 2) éléments en faveur de B, "
        "3) quels examens/infos discriminent A vs B."
    )
    result = await dispatcher.run(
        db,
        use_case=UseCase.UC1_DIAGNOSTIC,
        query=query,
        payload_for_routing=f"{req.symptoms} {req.option_a} {req.option_b}",
        system="Tu es un médecin interniste expert en raisonnement différentiel.",
        user_id=req.physician_id,
        patient_id=req.patient_id,
        metadata={"department": req.department, "mode": "explain_pair"},
        patient_context=merged_context,
        use_rag=False,
        max_tokens=420,
        temperature=0.1,
    )
    return ExplainDiagnosticResponse(
        explanation=result.response.text.strip(),
        provider_used=result.provider_used,
        model_used=result.model_used,
        rule=result.rule,
        audit_id=result.audit_id,
    )
