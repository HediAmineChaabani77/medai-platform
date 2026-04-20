"""Parser for BDPM (Base de Donnees Publique des Medicaments) open data.

Source: https://base-donnees-publique.medicaments.gouv.fr/telechargement
License: Licence Ouverte (Etalab) — compatible CC-BY 2.0 — commercial reuse with attribution.

Files are tab-separated, no header row, mixed encoding (mostly cp1252, sometimes utf-8).
Column specs from the official `Contenu_et_format_des_fichiers_telechargeables_dans_la_BDM_v4.pdf`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


ENCODINGS_TRY = ("utf-8", "cp1252", "latin-1")


def _open_bdpm(path: Path) -> Iterator[str]:
    """Yield decoded lines. Auto-detect encoding per-file."""
    raw = path.read_bytes()
    last_err: Exception | None = None
    for enc in ENCODINGS_TRY:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError as e:
            last_err = e
    else:
        raise last_err or UnicodeDecodeError("all", b"", 0, 1, "cannot decode")
    for line in text.splitlines():
        if line.strip():
            yield line


def _split(line: str, expected: int) -> list[str]:
    parts = line.split("\t")
    # Pad short rows (BDPM sometimes omits trailing empty tabs).
    while len(parts) < expected:
        parts.append("")
    return [p.strip() for p in parts[:expected]]


@dataclass
class Specialty:
    """CIS_bdpm.txt — one row per medication specialty."""
    cis: str
    name: str
    form: str
    routes: list[str]
    amm_status: str
    amm_procedure: str
    commercial_status: str
    amm_date: str
    bdm_status: str
    eu_authorization: str
    holders: list[str]
    reinforced_surveillance: bool

    @property
    def is_commercialised(self) -> bool:
        return self.commercial_status == "Commercialisée"


@dataclass
class Presentation:
    """CIS_CIP_bdpm.txt — one row per pack/box."""
    cis: str
    cip7: str
    label: str
    status: str
    commercial_status: str
    decl_date: str
    cip13: str
    collectivity_agreement: str
    reimbursement_rate: str
    price_eur: str
    public_price_eur: str
    dispensing_fee_eur: str
    reimbursement_indications: str


@dataclass
class Composition:
    """CIS_COMPO_bdpm.txt — one row per active substance within a specialty."""
    cis: str
    pharmaceutical_element: str
    substance_code: str
    substance_name: str  # DCI (dénomination commune internationale)
    dosage: str
    dosage_reference: str
    nature: str  # "SA" = substance active, "ST" = fraction thérapeutique
    link_number: str


@dataclass
class GenericGroup:
    """CIS_GENER_bdpm.txt — one row per (group, cis) pair."""
    group_id: str
    group_label: str
    cis: str
    type_code: str  # 0=princeps, 1=générique, 2=complémentarité, 4=substituable
    sort_order: str


@dataclass
class PrescriptionCondition:
    """CIS_CPD_bdpm.txt — one row per (cis, condition)."""
    cis: str
    condition: str


@dataclass
class SMROpinion:
    """CIS_HAS_SMR_bdpm.txt — HAS 'Service Médical Rendu' opinions."""
    cis: str
    has_dossier: str
    motive: str
    date: str  # YYYYMMDD
    smr_value: str
    smr_label: str


def parse_specialties(path: Path) -> Iterator[Specialty]:
    for line in _open_bdpm(path):
        c = _split(line, 12)
        yield Specialty(
            cis=c[0], name=c[1], form=c[2],
            routes=[x.strip() for x in c[3].split(";") if x.strip()],
            amm_status=c[4], amm_procedure=c[5], commercial_status=c[6],
            amm_date=c[7], bdm_status=c[8], eu_authorization=c[9],
            holders=[x.strip() for x in c[10].split(";") if x.strip()],
            reinforced_surveillance=(c[11].lower() == "oui"),
        )


def parse_presentations(path: Path) -> Iterator[Presentation]:
    for line in _open_bdpm(path):
        c = _split(line, 13)
        yield Presentation(
            cis=c[0], cip7=c[1], label=c[2], status=c[3], commercial_status=c[4],
            decl_date=c[5], cip13=c[6], collectivity_agreement=c[7],
            reimbursement_rate=c[8], price_eur=c[9], public_price_eur=c[10],
            dispensing_fee_eur=c[11], reimbursement_indications=c[12],
        )


def parse_compositions(path: Path) -> Iterator[Composition]:
    for line in _open_bdpm(path):
        c = _split(line, 8)
        yield Composition(
            cis=c[0], pharmaceutical_element=c[1], substance_code=c[2],
            substance_name=c[3], dosage=c[4], dosage_reference=c[5],
            nature=c[6], link_number=c[7],
        )


def parse_generic_groups(path: Path) -> Iterator[GenericGroup]:
    for line in _open_bdpm(path):
        c = _split(line, 5)
        yield GenericGroup(
            group_id=c[0], group_label=c[1], cis=c[2],
            type_code=c[3], sort_order=c[4],
        )


def parse_prescription_conditions(path: Path) -> Iterator[PrescriptionCondition]:
    for line in _open_bdpm(path):
        c = _split(line, 2)
        yield PrescriptionCondition(cis=c[0], condition=c[1])


def parse_smr_opinions(path: Path) -> Iterator[SMROpinion]:
    for line in _open_bdpm(path):
        c = _split(line, 6)
        yield SMROpinion(
            cis=c[0], has_dossier=c[1], motive=c[2],
            date=c[3], smr_value=c[4], smr_label=c[5],
        )


# ----- Cross-file joins and monograph synthesis -----

@dataclass
class DrugMonograph:
    """Denormalised view of one drug, built by joining BDPM files."""
    cis: str
    name: str
    form: str
    routes: list[str]
    holders: list[str]
    reinforced_surveillance: bool
    is_commercialised: bool
    amm_date: str
    substances: list[Composition] = field(default_factory=list)
    prescription_conditions: list[str] = field(default_factory=list)
    generic_group: tuple[str, str] | None = None  # (group_id, group_label)
    smr_opinions: list[SMROpinion] = field(default_factory=list)


def build_monographs(
    specialties_path: Path,
    compositions_path: Path,
    generics_path: Path,
    conditions_path: Path,
    smr_path: Path | None = None,
    commercialised_only: bool = True,
) -> Iterator[DrugMonograph]:
    """Join all BDPM files by CIS code and yield denormalised monographs."""
    # Preload smaller files into dicts keyed by CIS
    compositions_by_cis: dict[str, list[Composition]] = {}
    for c in parse_compositions(compositions_path):
        if c.nature == "SA":  # active substance only — skip fractions thérapeutiques
            compositions_by_cis.setdefault(c.cis, []).append(c)

    group_by_cis: dict[str, tuple[str, str]] = {}
    for g in parse_generic_groups(generics_path):
        group_by_cis[g.cis] = (g.group_id, g.group_label)

    conditions_by_cis: dict[str, list[str]] = {}
    for pc in parse_prescription_conditions(conditions_path):
        conditions_by_cis.setdefault(pc.cis, []).append(pc.condition)

    smr_by_cis: dict[str, list[SMROpinion]] = {}
    if smr_path and smr_path.exists():
        for s in parse_smr_opinions(smr_path):
            smr_by_cis.setdefault(s.cis, []).append(s)

    for sp in parse_specialties(specialties_path):
        if commercialised_only and not sp.is_commercialised:
            continue
        yield DrugMonograph(
            cis=sp.cis, name=sp.name, form=sp.form, routes=sp.routes,
            holders=sp.holders, reinforced_surveillance=sp.reinforced_surveillance,
            is_commercialised=sp.is_commercialised, amm_date=sp.amm_date,
            substances=compositions_by_cis.get(sp.cis, []),
            prescription_conditions=conditions_by_cis.get(sp.cis, []),
            generic_group=group_by_cis.get(sp.cis),
            smr_opinions=smr_by_cis.get(sp.cis, []),
        )


def monograph_to_markdown(m: DrugMonograph) -> str:
    """Render a monograph as citation-friendly markdown for the RAG index."""
    lines: list[str] = []
    lines.append(f"# {m.name}")
    lines.append("")
    lines.append(f"Source: BDPM (ANSM) — CIS {m.cis} — AMM du {m.amm_date or 'non renseignée'}")
    lines.append("")
    lines.append("## Forme et administration")
    lines.append(f"- Forme pharmaceutique: {m.form}")
    if m.routes:
        lines.append(f"- Voie(s) d'administration: {', '.join(m.routes)}")
    if m.holders:
        lines.append(f"- Titulaire(s) AMM: {', '.join(m.holders)}")
    if m.reinforced_surveillance:
        lines.append("- Surveillance renforcée (triangle noir): OUI")
    lines.append("")

    if m.substances:
        lines.append("## Composition (substances actives)")
        for s in m.substances:
            lines.append(f"- {s.substance_name} — {s.dosage} ({s.dosage_reference})")
        lines.append("")

    if m.prescription_conditions:
        lines.append("## Conditions de prescription et de délivrance")
        for cond in m.prescription_conditions:
            lines.append(f"- {cond}")
        lines.append("")

    if m.generic_group:
        gid, glabel = m.generic_group
        lines.append("## Groupe générique")
        lines.append(f"- Groupe {gid}: {glabel}")
        lines.append("")

    if m.smr_opinions:
        lines.append("## Avis HAS (Service Médical Rendu)")
        for s in m.smr_opinions[:5]:  # cap to keep chunks small
            d = s.date
            pretty = f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d) == 8 else d
            lines.append(f"- {pretty} — {s.motive}: SMR {s.smr_value}")
            if s.smr_label:
                lines.append(f"  {s.smr_label[:400]}")
        lines.append("")

    return "\n".join(lines)
