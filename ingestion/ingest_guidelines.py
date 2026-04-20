"""Ingest HAS/ESC/GINA guideline extracts (synthetic) into Qdrant."""
from _common import run

if __name__ == "__main__":
    run(source_label="Guidelines (synthetic)", glob_pattern="*_guideline.md")
