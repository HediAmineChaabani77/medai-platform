"""UC1 vignette harness.

Runs 30+ clinical vignettes through the heuristic fallback (no LLM call)
and asserts the expected condition appears in the top differential.

This measures the deterministic safety-net coverage — *the part that still
works when the LLM produces junk*. For end-to-end quality on live LLM,
run the same vignettes against the /api/uc1/diagnose endpoint.
"""
from __future__ import annotations

import pytest

from app.services.diagnostic_service import _heuristic_differential


VIGNETTES: list[tuple[str, str, dict, list[str]]] = [
    # (id, symptoms, patient_context, expected_conditions_any_of_these_in_top3)
    (
        "chest_pain_male",
        "douleur thoracique constrictive avec irradiation bras gauche et sueurs",
        {"age": 62, "sexe": "M"},
        ["Syndrome coronarien aigu", "Embolie pulmonaire"],
    ),
    (
        "chest_pain_dyspnea",
        "douleur thoracique aiguë avec dyspnée subite",
        {"age": 55, "sexe": "F"},
        ["Syndrome coronarien aigu", "Embolie pulmonaire", "Dissection aortique"],
    ),
    (
        "chest_pain_pericarditis_like",
        "douleur thoracique positionnelle soulagée par antéflexion",
        {"age": 35, "sexe": "M"},
        ["Péricardite aiguë", "Syndrome coronarien aigu"],
    ),
    (
        "uti_female",
        "dysurie et pollakiurie depuis 2 jours",
        {"age": 28, "sexe": "F"},
        ["Cystite aiguë simple"],
    ),
    (
        "uti_male",
        "pollakiurie avec brûlure mictionnelle",
        {"age": 55, "sexe": "M"},
        ["Cystite aiguë simple", "Prostatite aiguë"],
    ),
    (
        "uti_pyelonephritis",
        "dysurie associée à une fièvre 39 et douleur lombaire",
        {"age": 30, "sexe": "F"},
        ["Pyélonéphrite aiguë", "Cystite aiguë simple"],
    ),
    (
        "stroke_hemiparesis",
        "hémiparésie gauche d'apparition brutale avec aphasie",
        {"age": 70, "sexe": "M"},
        ["AVC ischémique", "Accident ischémique transitoire"],
    ),
    (
        "stroke_tia",
        "trouble neurologique transitoire avec déficit régressé en 1h",
        {"age": 65, "sexe": "F"},
        ["AVC ischémique", "Accident ischémique transitoire"],
    ),
    (
        "pneumonia",
        "fièvre 39 avec toux productive et dyspnée",
        {"age": 68, "sexe": "M"},
        ["Pneumonie communautaire", "Infection virale respiratoire (grippe/COVID-19)"],
    ),
    (
        "flu_like",
        "fièvre 38.5, toux sèche, asthénie et courbatures",
        {"age": 40, "sexe": "F"},
        ["Pneumonie communautaire", "Infection virale respiratoire (grippe/COVID-19)", "Bronchite aiguë"],
    ),
    (
        "bronchitis",
        "toux productive fébrile sans signe de gravité",
        {"age": 30, "sexe": "M"},
        ["Pneumonie communautaire", "Bronchite aiguë", "Infection virale respiratoire (grippe/COVID-19)"],
    ),
    # --- Abdominal pain
    (
        "appendicitis",
        "douleur abdominale fosse iliaque droite avec défense et fièvre",
        {"age": 20, "sexe": "M"},
        ["Appendicite aiguë"],
    ),
    (
        "cholecystitis",
        "douleur épigastrique irradiant hypochondre droit avec Murphy positif",
        {"age": 55, "sexe": "F"},
        ["Cholécystite aiguë", "Pancréatite aiguë"],
    ),
    (
        "pancreatitis",
        "douleur épigastrique transfixiante avec vomissements après repas gras",
        {"age": 48, "sexe": "M"},
        ["Pancréatite aiguë", "Cholécystite aiguë"],
    ),
    (
        "bowel_obstruction",
        "douleur abdominale avec arrêt des matières et vomissements bilieux",
        {"age": 75, "sexe": "F"},
        ["Occlusion intestinale", "Appendicite aiguë"],
    ),
    (
        "diverticulitis",
        "douleur abdominale FIG avec fièvre et modification du transit",
        {"age": 70, "sexe": "M"},
        ["Diverticulite sigmoïdienne", "Appendicite aiguë"],
    ),
    # --- Headache
    (
        "migraine",
        "céphalée pulsatile unilatérale avec photophobie et nausées",
        {"age": 32, "sexe": "F"},
        ["Migraine", "Céphalée de tension"],
    ),
    (
        "sah_thunderclap",
        "céphalée brutale en coup de tonnerre, la pire de ma vie",
        {"age": 50, "sexe": "M"},
        ["Hémorragie méningée", "Méningite"],
    ),
    (
        "meningitis",
        "céphalée avec fièvre et raideur de nuque",
        {"age": 22, "sexe": "M"},
        ["Méningite", "Migraine"],
    ),
    (
        "tension_headache",
        "céphalée bilatérale en étau sans signe d'alarme",
        {"age": 40, "sexe": "F"},
        ["Céphalée de tension", "Migraine"],
    ),
    # --- Dyspnea
    (
        "heart_failure_oap",
        "dyspnée d'effort avec orthopnée et œdèmes des membres inférieurs",
        {"age": 75, "sexe": "F"},
        ["Insuffisance cardiaque décompensée", "Embolie pulmonaire"],
    ),
    (
        "pe_isolated",
        "dyspnée aiguë brutale sans fièvre ni toux",
        {"age": 60, "sexe": "M"},
        ["Embolie pulmonaire", "Insuffisance cardiaque décompensée"],
    ),
    (
        "asthma_exacerbation",
        "dyspnée sifflante avec freinage expiratoire chez asthmatique connu",
        {"age": 28, "sexe": "F"},
        ["Exacerbation d'asthme / BPCO"],
    ),
    (
        "pneumothorax",
        "dyspnée brutale avec douleur latéralisée chez sujet jeune maigre",
        {"age": 22, "sexe": "M"},
        ["Pneumothorax spontané", "Embolie pulmonaire"],
    ),
    # --- Fever without obvious focus
    (
        "sepsis_suspect",
        "fièvre 39 avec frissons sans foyer clinique évident",
        {"age": 65, "sexe": "M"},
        ["Sepsis / bactériémie", "Pyélonéphrite aiguë", "Endocardite infectieuse"],
    ),
    (
        "endocarditis",
        "fièvre prolongée avec souffle cardiaque nouvellement apparu",
        {"age": 50, "sexe": "M"},
        ["Endocardite infectieuse", "Sepsis / bactériémie"],
    ),
    (
        "viral_infection",
        "fièvre modérée avec asthénie et myalgies diffuses",
        {"age": 30, "sexe": "F"},
        ["Infection virale systémique", "Sepsis / bactériémie"],
    ),
    # --- Syncope
    (
        "vasovagal_syncope",
        "malaise avec perte de connaissance brève après station debout prolongée",
        {"age": 25, "sexe": "F"},
        ["Syncope vagale", "Hypotension orthostatique"],
    ),
    (
        "arrhythmic_syncope",
        "syncope brutale sans prodrome à l'effort",
        {"age": 55, "sexe": "M"},
        ["Trouble du rythme (FA, BAV, TV)", "Syncope vagale"],
    ),
    (
        "orthostatic_hypo",
        "lipothymie au passage debout sous anti-HTA",
        {"age": 78, "sexe": "F"},
        ["Hypotension orthostatique", "Syncope vagale"],
    ),
    (
        "hypoglycemia_syncope",
        "malaise avec sueurs chez diabétique traité par insuline",
        {"age": 60, "sexe": "M"},
        ["Hypoglycémie", "Syncope vagale"],
    ),
]


@pytest.mark.parametrize("vid,symptoms,ctx,expected", VIGNETTES, ids=[v[0] for v in VIGNETTES])
def test_vignette_heuristic_fallback_top3(vid, symptoms, ctx, expected):
    diagnoses, red_flags = _heuristic_differential(symptoms, ctx)
    assert diagnoses, f"[{vid}] heuristic returned no differential"
    top = [d["condition"] for d in diagnoses[:3]]
    assert any(e in top for e in expected), (
        f"[{vid}] top3={top} did not match any of expected={expected}"
    )
    # Every vignette must also return at least one red-flag suggestion.
    assert red_flags, f"[{vid}] no red flags emitted"


def test_vignette_count():
    """Sanity: keep the vignette set broad enough to cover the major ER topoi."""
    assert len(VIGNETTES) >= 30
