from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import hash_patient_id
from app.core.dispatcher import LLMDispatcher
from app.core.router import UseCase
from app.models.report_archive import ReportArchive
from app.schemas.report import ReportRequest, ReportResponse, ReportSection
from app.services.dmp_service import get_patient_from_dmp, merge_uc2_context


TEMPLATES: dict[str, list[str]] = {
    "Consultation": ["Motif", "Anamnèse", "Examen clinique", "Conclusion", "Plan de soins"],
    "Hospitalisation": [
        "Motif d'hospitalisation",
        "Antécédents",
        "Histoire de la maladie",
        "Examen à l'admission",
        "Examens complémentaires",
        "Traitement institué",
        "Évolution",
        "Conclusion",
    ],
    "Opératoire": [
        "Indication",
        "Anesthésie",
        "Voie d'abord",
        "Déroulement",
        "Constatations",
        "Gestes réalisés",
        "Suites immédiates",
    ],
    "Urgences": [
        "Motif de consultation",
        "Anamnèse",
        "Constantes",
        "Examen clinique",
        "Examens complémentaires",
        "Diagnostic retenu",
        "Orientation",
    ],
}


SYSTEM_PROMPT = (
    "Tu es un secrétaire médical. Tu transformes des notes brutes en compte-rendu structuré en français. "
    "Tu respectes strictement les sections demandées. Tu n'inventes AUCUN fait clinique non présent dans les notes.\n\n"
    "Règles strictes de non-hallucination :\n"
    "- N'ajoute jamais de valeurs chiffrées (FC, PA, température, SpO2, âge, poids) si elles ne sont pas dans les notes.\n"
    "- N'infère jamais le sexe, l'âge ou les antécédents du patient à partir du prénom ou du contexte.\n"
    "- Si les notes disent 'Homme' ou 'Patient' au masculin, n'écris jamais 'Mme' ni 'femme'. Si 'Femme' ou 'Patiente' au féminin, n'écris jamais 'M.' ni 'homme'.\n"
    "- Ne prescris aucun médicament et ne propose aucun diagnostic absent des notes.\n"
    "- Si une section n'a pas d'information, écris 'Non renseigné'. Ne l'invente pas.\n"
    "- Français clinique standard uniquement. Pas d'anglicismes.\n\n"
    "N'ajoute pas de section 'Sources' si aucun contexte documentaire n'est fourni."
)


def _build_query(req: ReportRequest, sections: list[str]) -> str:
    ctx = json.dumps(req.patient_context, ensure_ascii=False)
    section_list = "\n".join(f"- {s}" for s in sections)
    return (
        f"Type de compte-rendu: {req.report_type}\n"
        f"Contexte patient: {ctx}\n\n"
        f"Notes brutes:\n{req.raw_text}\n\n"
        f"Rédige le compte-rendu en markdown avec EXACTEMENT ces sections (dans l'ordre), chacune en titre de niveau 2 (##):\n{section_list}"
    )


def _parse_markdown_sections(md: str, expected: list[str]) -> list[ReportSection]:
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    def _extract_by_heading_level(text: str, level: str) -> list[ReportSection]:
        out_local: list[ReportSection] = []
        parts = re.split(rf"(?m)^{re.escape(level)}\s+", text)
        # First part may be preamble — drop if before any header
        for p in parts:
            p = p.strip()
            if not p:
                continue
            lines = p.splitlines()
            title = lines[0].strip().lstrip("#").strip()
            body = "\n".join(lines[1:]).strip()
            if not title:
                continue
            out_local.append(ReportSection(title=title, content=body))
        return out_local

    out = _extract_by_heading_level(md, "##")
    expected_norm = {_norm(e) for e in expected}
    if len(out) == 1 and _norm(out[0].title) not in expected_norm:
        nested = _extract_by_heading_level(out[0].content, "###")
        if nested:
            out = nested

    # Re-map to expected template order and fill gaps with placeholders.
    aligned: list[ReportSection] = []
    used_indices: set[int] = set()
    for exp in expected:
        exp_norm = _norm(exp)
        chosen_idx = None
        for idx, sec in enumerate(out):
            if idx in used_indices:
                continue
            sec_norm = _norm(sec.title)
            if sec_norm == exp_norm or exp_norm in sec_norm or sec_norm in exp_norm:
                chosen_idx = idx
                break
        if chosen_idx is None:
            aligned.append(ReportSection(title=exp, content="Non renseigné"))
        else:
            used_indices.add(chosen_idx)
            aligned.append(ReportSection(title=exp, content=out[chosen_idx].content))

    if any(s.content != "Non renseigné" for s in aligned):
        return aligned

    # Last-resort fallback if we failed to map any section at all.
    return [ReportSection(title=s, content=md.strip()) for s in expected[:1]] + [
        ReportSection(title=s, content="Non renseigné") for s in expected[1:]
    ]


def sign_report(markdown: str, physician_key: str | None) -> str:
    key = (physician_key or "unsigned").encode("utf-8")
    return hmac.new(key, markdown.encode("utf-8"), hashlib.sha256).hexdigest()


def transcribe_audio_local(audio_path: Path, language: str = "fr") -> str:
    """Local Whisper transcription via faster-whisper. Runs fully offline."""
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), language=language, vad_filter=True)
    return " ".join(seg.text for seg in segments).strip()


async def run_report(
    db: Session,
    dispatcher: LLMDispatcher,
    req: ReportRequest,
) -> ReportResponse:
    dmp_record = get_patient_from_dmp(req.patient_id, get_settings())
    merged_context = merge_uc2_context(req.patient_context, dmp_record)
    sections = TEMPLATES[req.report_type]
    req_for_build = req.model_copy(update={"patient_context": merged_context})
    query = _build_query(req_for_build, sections)

    result = await dispatcher.run(
        db,
        use_case=UseCase.UC2_REPORT,
        query=query,
        payload_for_routing=req.raw_text,
        system=SYSTEM_PROMPT,
        user_id=req.physician_id,
        patient_id=req.patient_id,
        metadata={"department": req.department, "report_type": req.report_type},
        patient_context=merged_context,
        # BDPM monographs are weak context for narrative report structuring.
        use_rag=False,
        max_tokens=1200,
        temperature=0.2,
    )

    markdown = result.response.text
    parsed_sections = _parse_markdown_sections(markdown, sections)
    signature = sign_report(markdown, req.physician_key)

    return ReportResponse(
        report_type=req.report_type,
        markdown=markdown,
        sections=parsed_sections,
        signature=signature,
        provider_used=result.provider_used,
        model_used=result.model_used,
        rule=result.rule,
        audit_id=result.audit_id,
        citations=result.citations,
    )


def archive_report(
    db: Session,
    *,
    patient_id: str | None,
    report_type: str,
    markdown: str,
    signature: str,
    signed_by: str | None,
    destination: str = "DPI",
) -> ReportArchive:
    settings = get_settings()
    archive_dir = Path(settings.dpi_archive_dir)
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        archive_dir = Path("/tmp/medai_dpi_archive")
        archive_dir.mkdir(parents=True, exist_ok=True)

    row = ReportArchive(
        patient_id_hash=hash_patient_id(patient_id),
        report_type=report_type,
        signed_by=signed_by,
        signature=signature,
        destination=destination or "DPI",
        archive_path="",  # set after insert to include ID
        markdown=markdown,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    filename = f"report_{row.id}_{report_type}.md".replace(" ", "_")
    path = archive_dir / filename
    path.write_text(markdown, encoding="utf-8")
    row.archive_path = str(path)
    db.commit()
    db.refresh(row)
    return row
