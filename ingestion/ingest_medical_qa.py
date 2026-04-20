"""Ingest medical_qa.json into Qdrant as the ONLY RAG dataset.

Input dataset:
    C:/Users/MSI/Documents/Med_LLM/medical_qa.json
or
    /mnt/c/Users/MSI/Documents/Med_LLM/medical_qa.json

The script wipes the target Qdrant collection and re-indexes only this file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent
for _c in (_HERE.parent.parent, _HERE.parent.parent / "backend", Path("/app")):
    if (_c / "app" / "config.py").is_file():
        sys.path.insert(0, str(_c))
        ROOT = _c if _c.name != "backend" else _c.parent
        break

from app.config import get_settings  # noqa: E402
from app.core.llm_provider import build_local_provider  # noqa: E402
from app.core.rag import Chunk, RAGIndex, chunk_text  # noqa: E402


def _default_dataset_path() -> Path:
    candidates = [
        Path("/mnt/c/Users/MSI/Documents/Med_LLM/medical_qa.json"),
        Path("/mnt/c/users/msi/documents/med_llm/medical_qa.json"),
        Path("C:/Users/MSI/Documents/Med_LLM/medical_qa.json"),
        ROOT / "backend" / "data" / "knowledge_base" / "medical_qa.json",
        ROOT / "data" / "knowledge_base" / "medical_qa.json",
        Path("/app/data/knowledge_base/medical_qa.json"),
        ROOT.parent / "medical_qa.json",
        ROOT / "medical_qa.json",
        Path("/app/medical_qa.json"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\ufeff", " ")
    s = s.replace("❓", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


@dataclass
class QAItem:
    idx: int
    category: str
    question: str
    answer: str


def load_items(path: Path) -> list[QAItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    categories = raw.get("categories", []) if isinstance(raw, dict) else []
    out: list[QAItem] = []
    i = 0
    for cat in categories:
        category = _clean_text((cat or {}).get("category", "General"))
        for qa in (cat or {}).get("questions", []) or []:
            q = _clean_text((qa or {}).get("question", ""))
            a = _clean_text((qa or {}).get("answer", ""))
            if not q or not a:
                continue
            i += 1
            out.append(QAItem(idx=i, category=category or "General", question=q, answer=a))
    return out


def build_chunks(items: list[QAItem], size_tokens: int = 180, overlap: int = 30) -> list[Chunk]:
    chunks: list[Chunk] = []
    for item in items:
        text = (
            f"Category: {item.category}\n"
            f"Question: {item.question}\n"
            f"Answer: {item.answer}"
        )
        # Keep each QA pair coherent; split only if an answer is unusually long.
        pieces = chunk_text(
            text=text,
            size_tokens=size_tokens,
            overlap=overlap,
            section_header=f"{item.category} | QA#{item.idx}",
        )
        for j, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    id=f"medical_qa:{item.idx}:{j}",
                    text=piece,
                    metadata={
                        "source": "medical_qa.json",
                        "section": item.category,
                        "qa_index": item.idx,
                    },
                )
            )
    return chunks


async def ingest(chunks: list[Chunk], clear_collection: bool = True, concurrency: int = 8):
    settings = get_settings()
    provider = build_local_provider(settings)
    rag = RAGIndex(settings.qdrant_url, settings.qdrant_collection, embed_fn=provider.embed)

    if clear_collection:
        client = QdrantClient(url=settings.qdrant_url)
        names = {c.name for c in client.get_collections().collections}
        if settings.qdrant_collection in names:
            client.delete_collection(settings.qdrant_collection)
    rag.ensure_collection()

    batch_size = 64
    total = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        await rag.upsert(batch, concurrency=concurrency)
        total += len(batch)
        print(f"... indexed {total}/{len(chunks)} chunks", flush=True)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=_default_dataset_path())
    ap.add_argument("--size-tokens", type=int, default=180)
    ap.add_argument("--overlap", type=int, default=30)
    ap.add_argument("--no-clear", action="store_true", help="Do not wipe collection before ingest")
    args = ap.parse_args()

    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}")
        sys.exit(2)

    items = load_items(args.dataset)
    if not items:
        print("No QA items found in dataset.")
        sys.exit(3)

    chunks = build_chunks(items, size_tokens=args.size_tokens, overlap=args.overlap)
    print(f"Loaded {len(items)} QA pairs -> {len(chunks)} chunks")
    total = asyncio.run(ingest(chunks, clear_collection=not args.no_clear))
    print(f"Done. Indexed {total} chunks into collection '{get_settings().qdrant_collection}'.")


if __name__ == "__main__":
    main()
