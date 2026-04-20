"""Ingest BDPM (ANSM) open data into Postgres and Qdrant.

Source files must be placed in: backend/data/raw/bdpm/
  - CIS_bdpm.txt           (specialties, ~15k rows)
  - CIS_COMPO_bdpm.txt     (compositions)
  - CIS_GENER_bdpm.txt     (generic groups)
  - CIS_CPD_bdpm.txt       (prescription conditions)
  - CIS_HAS_SMR_bdpm.txt   (HAS SMR opinions — optional)

License: Licence Ouverte (Etalab), compatible CC-BY 2.0. Reuse requires
attribution ("Source: BDPM — ANSM — <last updated date>").

Usage:
    python ingestion/ingest_bdpm.py                   # ingest all commercialised drugs
    python ingestion/ingest_bdpm.py --limit 500       # cap for smoke testing
    python ingestion/ingest_bdpm.py --rag-limit 1000  # cap RAG indexing volume
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT_CANDIDATES = [_HERE.parent.parent, _HERE.parent.parent / "backend", Path("/app")]
ROOT = _HERE.parent.parent
for _c in _ROOT_CANDIDATES:
    if (_c / "app" / "config.py").is_file():
        sys.path.insert(0, str(_c))
        ROOT = _c if _c.name != "backend" else _c.parent
        break


def _find_data(sub: str) -> Path:
    for base in (ROOT / "backend" / "data", ROOT / "data", Path("/app/data")):
        p = base / sub
        if p.exists() or base.exists():
            return p
    return ROOT / "backend" / "data" / sub


from app.config import get_settings  # noqa: E402
from app.core.bdpm_parser import (  # noqa: E402
    DrugMonograph, build_monographs, monograph_to_markdown,
)
from app.core.llm_provider import build_local_provider  # noqa: E402
from app.core.rag import Chunk, RAGIndex, chunk_text  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.drug import Drug, DrugComposition, DrugInteraction, GenericGroupEntry  # noqa: E402


BDPM_DIR = _find_data("raw/bdpm")
KB_DIR = _find_data("knowledge_base")


def _paths() -> dict[str, Path]:
    return {
        "spec": BDPM_DIR / "CIS_bdpm.txt",
        "compo": BDPM_DIR / "CIS_COMPO_bdpm.txt",
        "gener": BDPM_DIR / "CIS_GENER_bdpm.txt",
        "cpd": BDPM_DIR / "CIS_CPD_bdpm.txt",
        "smr": BDPM_DIR / "CIS_HAS_SMR_bdpm.txt",
    }


def check_sources(paths: dict[str, Path]) -> list[str]:
    missing = [name for name, p in paths.items() if name != "smr" and not p.exists()]
    return missing


def ingest_postgres(monographs: list[DrugMonograph]) -> dict[str, int]:
    Base.metadata.create_all(bind=engine)
    counts = {"drugs": 0, "compositions": 0, "generic_entries": 0}
    with SessionLocal() as db:
        # Wipe and repopulate — idempotent. For incremental updates, compare mtimes.
        db.query(DrugComposition).delete()
        db.query(GenericGroupEntry).delete()
        db.query(Drug).delete()
        db.commit()

        for m in monographs:
            drug = Drug(
                cis=m.cis, name=m.name, form=m.form,
                routes=";".join(m.routes) or None,
                holders=";".join(m.holders) or None,
                amm_date=m.amm_date,
                commercial_status="Commercialisée" if m.is_commercialised else "",
                reinforced_surveillance=m.reinforced_surveillance,
            )
            db.add(drug)
            counts["drugs"] += 1
            for s in m.substances:
                db.add(DrugComposition(
                    cis=m.cis, substance_code=s.substance_code,
                    substance_name=s.substance_name, dosage=s.dosage,
                    dosage_reference=s.dosage_reference,
                ))
                counts["compositions"] += 1
            if m.generic_group:
                gid, glabel = m.generic_group
                db.add(GenericGroupEntry(
                    group_id=gid, group_label=glabel, cis=m.cis, type_code="0",
                ))
                counts["generic_entries"] += 1

        db.commit()
    return counts


def ingest_manual_interactions(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    count = 0
    with SessionLocal() as db, csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            src = row.get("source") or "manual"
            exists = (
                db.query(DrugInteraction)
                .filter_by(drug_a=row["drug_a"].lower(), drug_b=row["drug_b"].lower(), source=src)
                .first()
            )
            if exists:
                continue
            db.add(DrugInteraction(
                drug_a=row["drug_a"].lower(),
                drug_b=row["drug_b"].lower(),
                severity=row["severity"].lower(),
                mechanism=row["mechanism"],
                note=row.get("note"),
                source=src,
            ))
            count += 1
        db.commit()
    return count


async def ingest_rag(monographs: list[DrugMonograph], rag_limit: int | None) -> int:
    settings = get_settings()
    provider = build_local_provider(settings)
    rag = RAGIndex(settings.qdrant_url, settings.qdrant_collection, embed_fn=provider.embed)
    rag.ensure_collection()

    items = monographs[:rag_limit] if rag_limit else monographs
    all_chunks: list[Chunk] = []
    for m in items:
        md = monograph_to_markdown(m)
        # Section headers inside the monograph are consistent. Chunk whole doc.
        for j, piece in enumerate(chunk_text(md, size_tokens=512, overlap=64, section_header=m.name)):
            all_chunks.append(Chunk(
                id=f"bdpm:{m.cis}:{j}",
                text=piece,
                metadata={
                    "source": "BDPM (ANSM)",
                    "section": m.name,
                    "url_or_page": f"CIS {m.cis}",
                    "last_updated": "2025-08",
                    "cis": m.cis,
                    "active_ingredients": [s.substance_name for s in m.substances],
                },
            ))

    batch: list[Chunk] = []
    total = 0
    for ch in all_chunks:
        batch.append(ch)
        if len(batch) >= 64:
            await rag.upsert(batch)
            total += len(batch)
            print(f"  ... indexed {total}/{len(all_chunks)} chunks", flush=True)
            batch.clear()
    if batch:
        await rag.upsert(batch)
        total += len(batch)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Cap number of monographs to process")
    ap.add_argument("--rag-limit", type=int, default=None, help="Cap monographs indexed into Qdrant")
    ap.add_argument("--skip-rag", action="store_true", help="Skip Qdrant indexing (Postgres only)")
    ap.add_argument("--skip-interactions", action="store_true", help="Skip manual-seed interactions CSV")
    args = ap.parse_args()

    paths = _paths()
    missing = check_sources(paths)
    if missing:
        print("ERROR: missing BDPM files in backend/data/raw/bdpm/:", missing)
        print("Download from https://base-donnees-publique.medicaments.gouv.fr/telechargement")
        sys.exit(2)

    print("Building monographs from BDPM...")
    monographs = list(build_monographs(
        paths["spec"], paths["compo"], paths["gener"], paths["cpd"],
        smr_path=paths["smr"] if paths["smr"].exists() else None,
        commercialised_only=True,
    ))
    if args.limit:
        monographs = monographs[: args.limit]
    print(f"  built {len(monographs)} commercialised drug monographs")

    print("Ingesting into Postgres...")
    counts = ingest_postgres(monographs)
    print(f"  drugs={counts['drugs']} compositions={counts['compositions']} generic_entries={counts['generic_entries']}")

    if not args.skip_interactions:
        n = ingest_manual_interactions(KB_DIR / "drug_interactions.csv")
        print(f"  seeded {n} manual drug interactions")

    if args.skip_rag:
        print("Skipping RAG indexing.")
        return

    print("Indexing monographs into Qdrant (local embeddings)...")
    total = asyncio.run(ingest_rag(monographs, args.rag_limit))
    print(f"  indexed {total} chunks")
    print("Done.")


if __name__ == "__main__":
    main()
