"""Vidal / Thériaque ingestion.

Vidal and Thériaque are proprietary French drug databases (paid license).
This script is a placeholder that exits 0 until a license decision is made.

For now, French drug data is supplied by BDPM (ANSM open data) via
`ingest_bdpm.py`. BDPM covers ~13,500 commercialised specialties with
compositions, generic groups, prescription conditions, and HAS SMR opinions.

When a Vidal/Thériaque feed becomes available (CSV, XML, or SQL dump),
extend this script with a parser that normalises records into the same
`drugs`, `drug_compositions`, and `drug_interactions` tables, and tags
each row with `source='vidal'` or `source='theriaque'` so RAG citations
remain traceable.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    vidal_dir = ROOT / "backend" / "data" / "raw" / "vidal"
    theriaque_dir = ROOT / "backend" / "data" / "raw" / "theriaque"
    if not vidal_dir.exists() and not theriaque_dir.exists():
        print("No Vidal/Thériaque source files found — nothing to ingest.")
        print("Current French drug knowledge comes from BDPM (ingest_bdpm.py).")
        return 0
    print("Vidal/Thériaque parsers are not implemented in this build.")
    print("See the docstring of ingestion/ingest_vidal.py for integration guidance.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
