"""Ingest DrugBank Open Data (drug-drug interactions) into Postgres.

DrugBank Open Data XML is distributed under CC-BY-NC 4.0 (research only).
You must create a free account at https://go.drugbank.com and download
`drugbank_all_full_database.xml` or the "Open Data" subset.

Place the file at:
    backend/data/raw/drugbank/drugbank_open_data.xml

This script extracts pairwise drug-drug interactions and writes them to
the `drug_interactions` table with source='drugbank_open'. Drug names are
lowercased; pair order is normalised (alphabetical) to avoid duplicates.

If the file is not present, the script exits 0 and leaves whatever manual
seed interactions already loaded via ingest_bdpm.py intact.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent
for _c in (_HERE.parent.parent, _HERE.parent.parent / "backend", Path("/app")):
    if (_c / "app" / "config.py").is_file():
        sys.path.insert(0, str(_c))
        ROOT = _c if _c.name != "backend" else _c.parent
        break

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.drug import DrugInteraction  # noqa: E402


def _data_root() -> Path:
    for base in (ROOT / "backend" / "data", ROOT / "data", Path("/app/data")):
        if base.exists():
            return base
    return ROOT / "backend" / "data"


DRUGBANK_XML = _data_root() / "raw" / "drugbank" / "drugbank_open_data.xml"
NS = {"db": "http://www.drugbank.ca"}


SEVERITY_HEURISTIC = {
    "major": ("serious", "severe", "major", "life-threatening", "contraindicat", "avoid"),
    "moderate": ("moderate", "monitor", "caution", "reduce"),
    "minor": ("minor", "mild"),
}


def infer_severity(text: str) -> str:
    low = (text or "").lower()
    for level, markers in SEVERITY_HEURISTIC.items():
        if any(m in low for m in markers):
            return level
    return "moderate"


def run():
    if not DRUGBANK_XML.exists():
        print(f"DrugBank XML not found at {DRUGBANK_XML}. Skipping (this is fine).")
        print("To enable: place `drugbank_open_data.xml` in backend/data/raw/drugbank/")
        return

    Base.metadata.create_all(bind=engine)
    print(f"Parsing {DRUGBANK_XML} (streaming)...")

    count = 0
    # Streaming parse — DrugBank Open Data XML can exceed 1 GB.
    context = ET.iterparse(str(DRUGBANK_XML), events=("end",))
    with SessionLocal() as db:
        for _, elem in context:
            tag = elem.tag.split("}", 1)[-1]
            if tag != "drug":
                continue
            name_el = elem.find("db:name", NS)
            if name_el is None or not name_el.text:
                elem.clear()
                continue
            drug_a = name_el.text.strip().lower()
            interactions = elem.find("db:drug-interactions", NS)
            if interactions is not None:
                for di in interactions.findall("db:drug-interaction", NS):
                    partner = di.find("db:name", NS)
                    desc = di.find("db:description", NS)
                    if partner is None or not partner.text:
                        continue
                    drug_b = partner.text.strip().lower()
                    if drug_a >= drug_b:
                        continue  # dedupe via alphabetical order
                    mechanism = (desc.text or "").strip() if desc is not None else ""
                    severity = infer_severity(mechanism)
                    row = (
                        db.query(DrugInteraction)
                        .filter_by(drug_a=drug_a, drug_b=drug_b, source="drugbank_open")
                        .first()
                    )
                    if row:
                        continue
                    db.add(DrugInteraction(
                        drug_a=drug_a, drug_b=drug_b, severity=severity,
                        mechanism=mechanism[:4000], note=None,
                        source="drugbank_open",
                    ))
                    count += 1
                    if count % 1000 == 0:
                        db.commit()
                        print(f"  ... {count} interactions", flush=True)
            elem.clear()
        db.commit()

    print(f"Ingested {count} DrugBank Open Data interactions.")


if __name__ == "__main__":
    run()
