from __future__ import annotations

import asyncio
import hashlib
import re
import sys
from pathlib import Path

# Detect repo-root layout ({repo}/backend/app) vs container layout ({/app}/app).
_HERE = Path(__file__).resolve()
_CANDIDATE_ROOTS = [_HERE.parent.parent, _HERE.parent.parent / "backend", Path("/app")]
ROOT = _HERE.parent.parent
for _c in _CANDIDATE_ROOTS:
    if (_c / "app" / "config.py").is_file():
        sys.path.insert(0, str(_c))
        ROOT = _c if (_c.name != "backend") else _c.parent
        break


def resolve_data_dir(sub: str) -> Path:
    """Locate data/<sub> across host (backend/data/...) and container (data/...) layouts."""
    for base in (ROOT / "backend" / "data", ROOT / "data", Path("/app/data")):
        p = base / sub
        if p.exists():
            return p
    return ROOT / "backend" / "data" / sub


from app.config import get_settings  # noqa: E402
from app.core.llm_provider import build_local_provider  # noqa: E402
from app.core.rag import Chunk, RAGIndex, chunk_text  # noqa: E402


def doc_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]


def parse_sections(md_text: str) -> list[tuple[str, str]]:
    """Split markdown into (section_header, body) pairs using H1/H2."""
    lines = md_text.splitlines()
    sections: list[tuple[str, str]] = []
    cur_header = "root"
    cur_body: list[str] = []
    for line in lines:
        m = re.match(r"^#{1,2}\s+(.*)", line)
        if m:
            if cur_body:
                sections.append((cur_header, "\n".join(cur_body).strip()))
                cur_body = []
            cur_header = m.group(1).strip()
        else:
            cur_body.append(line)
    if cur_body:
        sections.append((cur_header, "\n".join(cur_body).strip()))
    return [(h, b) for h, b in sections if b]


def build_chunks_from_markdown(path: Path, source_label: str) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    did = doc_id(path)
    chunks: list[Chunk] = []
    for i, (header, body) in enumerate(parse_sections(text)):
        for j, piece in enumerate(chunk_text(body, size_tokens=512, overlap=64, section_header=header)):
            cid = f"{did}:{i}:{j}"
            chunks.append(
                Chunk(
                    id=cid,
                    text=piece,
                    metadata={
                        "source": source_label,
                        "section": header,
                        "url_or_page": str(path.name),
                        "last_updated": "2026-01-01",
                    },
                )
            )
    return chunks


async def ingest_paths(paths: list[Path], source_label: str):
    settings = get_settings()
    provider = build_local_provider(settings)
    rag = RAGIndex(settings.qdrant_url, settings.qdrant_collection, embed_fn=provider.embed)
    all_chunks: list[Chunk] = []
    for p in paths:
        all_chunks.extend(build_chunks_from_markdown(p, source_label))
    print(f"Ingesting {len(all_chunks)} chunks from {len(paths)} files into '{settings.qdrant_collection}'")
    await rag.upsert(all_chunks)
    print("Done.")


def run(source_label: str, glob_pattern: str):
    kb = resolve_data_dir("knowledge_base")
    paths = sorted(kb.glob(glob_pattern))
    if not paths:
        print(f"No files found matching {glob_pattern} under {kb}")
        return
    asyncio.run(ingest_paths(paths, source_label))
