from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from rank_bm25 import BM25Okapi


WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


@dataclass
class Retrieval:
    chunk: Chunk
    score: float
    rank_dense: int | None = None
    rank_bm25: int | None = None


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(text or "")]


def chunk_text(text: str, size_tokens: int = 512, overlap: int = 64, section_header: str | None = None) -> list[str]:
    """Approximate token-count chunking using whitespace tokens. Preserves header at start of each chunk."""
    tokens = text.split()
    out: list[str] = []
    if not tokens:
        return out
    step = max(1, size_tokens - overlap)
    for start in range(0, len(tokens), step):
        piece = " ".join(tokens[start : start + size_tokens])
        if section_header:
            piece = f"[{section_header}]\n{piece}"
        out.append(piece)
        if start + size_tokens >= len(tokens):
            break
    return out


class RAGIndex:
    """Hybrid dense (Qdrant) + BM25 (in-memory) index with RRF fusion."""

    DIM = 768

    def __init__(
        self,
        qdrant_url: str,
        collection: str,
        embed_fn,
        client: QdrantClient | None = None,
    ):
        self.collection = collection
        self.embed_fn = embed_fn  # async callable: text -> list[float]
        self.client = client or QdrantClient(url=qdrant_url)
        self._bm25: BM25Okapi | None = None
        self._bm25_ids: list[str] = []
        self._bm25_corpus_texts: list[str] = []
        self._bm25_payloads: list[dict] = []

    def ensure_collection(self):
        names = {c.name for c in self.client.get_collections().collections}
        if self.collection not in names:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=self.DIM, distance=qm.Distance.COSINE),
            )

    def _point_id(self, chunk_id: str) -> int:
        # Qdrant point ids are int or UUID. Derive stable int from string.
        return abs(hash(chunk_id)) % (2**63 - 1)

    async def upsert(self, chunks: Iterable[Chunk], concurrency: int = 8):
        self.ensure_collection()
        import asyncio

        chunks = list(chunks)
        sem = asyncio.Semaphore(concurrency)

        async def embed_one(ch: Chunk):
            async with sem:
                vec = await self.embed_fn(ch.text)
                payload = {"text": ch.text, "chunk_id": ch.id, **ch.metadata}
                return qm.PointStruct(id=self._point_id(ch.id), vector=vec, payload=payload)

        points = await asyncio.gather(*(embed_one(ch) for ch in chunks))
        if points:
            self.client.upsert(collection_name=self.collection, points=points)
        self._refresh_bm25()

    def _refresh_bm25(self):
        # Load all points from Qdrant to rebuild BM25. OK for corpus < ~100k chunks.
        self._bm25_ids = []
        self._bm25_corpus_texts = []
        self._bm25_payloads = []
        scroll = self.client.scroll(collection_name=self.collection, limit=10000, with_payload=True)
        records = scroll[0] if isinstance(scroll, tuple) else scroll
        for rec in records:
            payload = rec.payload or {}
            self._bm25_ids.append(payload.get("chunk_id") or str(rec.id))
            self._bm25_corpus_texts.append(payload.get("text", ""))
            self._bm25_payloads.append(payload)
        if self._bm25_corpus_texts:
            self._bm25 = BM25Okapi([tokenize(t) for t in self._bm25_corpus_texts])

    async def retrieve(self, query: str, top_k: int = 5, rerank: bool = True) -> list[Retrieval]:
        """Hybrid retrieval:
        1. top-10 dense + top-10 BM25
        2. reciprocal rank fusion -> top_fuse (larger candidate set)
        3. cross-encoder reranker (BAAI/bge-reranker-v2-m3, CPU) collapses to top_k
        """
        self.ensure_collection()
        if self._bm25 is None:
            self._refresh_bm25()

        # Dense
        qvec = await self.embed_fn(query)
        dense_hits = self.client.search(
            collection_name=self.collection, query_vector=qvec, limit=10, with_payload=True
        )
        dense_map: dict[str, tuple[int, dict]] = {}
        for i, hit in enumerate(dense_hits):
            payload = hit.payload or {}
            cid = payload.get("chunk_id") or str(hit.id)
            dense_map[cid] = (i + 1, payload)

        # BM25
        bm25_map: dict[str, tuple[int, dict]] = {}
        if self._bm25 and self._bm25_corpus_texts:
            scores = self._bm25.get_scores(tokenize(query))
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:10]
            for rank, idx in enumerate(ranked):
                cid = self._bm25_ids[idx]
                payload = dict(self._bm25_payloads[idx])
                payload.setdefault("chunk_id", cid)
                payload.setdefault("text", self._bm25_corpus_texts[idx])
                bm25_map[cid] = (rank + 1, payload)

        # RRF fusion (k=60)
        k_rrf = 60
        scores: dict[str, dict] = {}
        for cid, (rank, payload) in dense_map.items():
            s = scores.setdefault(cid, {"score": 0.0, "payload": payload, "rank_dense": None, "rank_bm25": None})
            s["score"] += 1.0 / (k_rrf + rank)
            s["rank_dense"] = rank
            s["payload"] = payload
        for cid, (rank, payload) in bm25_map.items():
            s = scores.setdefault(cid, {"score": 0.0, "payload": payload, "rank_dense": None, "rank_bm25": None})
            s["score"] += 1.0 / (k_rrf + rank)
            s["rank_bm25"] = rank
            if s["payload"].get("text") is None:
                s["payload"] = payload

        # Keep a larger candidate set for the reranker; collapse to top_k after.
        fuse_k = max(20, top_k * 4) if rerank else top_k
        fused = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)[:fuse_k]

        out: list[Retrieval] = []
        for cid, info in fused:
            p = info["payload"]
            chunk = Chunk(id=cid, text=p.get("text", ""), metadata={k: v for k, v in p.items() if k not in ("text", "chunk_id")})
            out.append(Retrieval(chunk=chunk, score=info["score"], rank_dense=info["rank_dense"], rank_bm25=info["rank_bm25"]))

        if rerank and out:
            out = _rerank(query, out, top_k=top_k)
        else:
            out = out[:top_k]
        return out


_RERANKER = None


def _get_reranker():
    """Lazy-load the cross-encoder. CPU-only so it doesn't fight the GPU LLM."""
    global _RERANKER
    if _RERANKER is None:
        try:
            from sentence_transformers import CrossEncoder
            _RERANKER = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512, device="cpu")
        except Exception:
            _RERANKER = False  # sentinel so we don't retry every call
    return _RERANKER


def _rerank(query: str, retrievals: list["Retrieval"], top_k: int) -> list["Retrieval"]:
    model = _get_reranker()
    if not model:
        return retrievals[:top_k]
    pairs = [(query, r.chunk.text) for r in retrievals]
    scores = model.predict(pairs)
    for r, s in zip(retrievals, scores):
        r.score = float(s)
    retrievals.sort(key=lambda r: r.score, reverse=True)
    return retrievals[:top_k]


def build_rag_prompt(question: str, retrievals: list[Retrieval]) -> tuple[str, list[dict]]:
    """Build a citation-aware user prompt. Returns (prompt, citations)."""
    lines = ["Contexte documentaire (utilise UNIQUEMENT ces extraits, cite les IDs entre crochets):\n"]
    citations = []
    for i, r in enumerate(retrievals, start=1):
        cid = f"SRC{i}"
        source = r.chunk.metadata.get("source", "unknown")
        section = r.chunk.metadata.get("section", "")
        lines.append(f"[{cid}] ({source} — {section})\n{r.chunk.text}\n")
        citations.append({"id": cid, "source": source, "section": section, "chunk_id": r.chunk.id, "metadata": r.chunk.metadata})
    lines.append(f"\nQuestion: {question}\n")
    lines.append("Règles: Si l'information n'est pas dans le contexte, réponds 'information générale, non clinique'. Cite les sources utilisées comme [SRC1], [SRC2], etc.")
    return "\n".join(lines), citations
