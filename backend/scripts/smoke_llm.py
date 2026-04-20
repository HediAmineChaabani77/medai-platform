"""Light smoke test of the local LLM + embeddings via Ollama.

Run from inside the backend container:
    docker compose exec backend python scripts/smoke_llm.py

Or on the host with Ollama reachable at localhost:
    OLLAMA_HOST=http://localhost:11434 python backend/scripts/smoke_llm.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.core.llm_provider import build_local_provider


async def main():
    settings = get_settings()
    provider = build_local_provider(settings)
    print(f"Ollama host: {settings.ollama_host}")
    print(f"LLM model:   {settings.llm_local_model}")
    print(f"Embed model: {settings.llm_embed_model}")
    print()

    print("[1/2] Generation...")
    r = await provider.generate(
        "Répondez en une phrase: qu'est-ce que l'hypertension ?",
        system="Tu es un médecin. Réponse courte.",
        max_tokens=80,
        temperature=0.1,
    )
    print(f"  provider={r.provider} model={r.model}")
    print(f"  prompt_tokens={r.prompt_tokens} completion_tokens={r.completion_tokens}")
    print(f"  text: {r.text.strip()[:300]}")
    print()

    print("[2/2] Embedding...")
    v = await provider.embed("hypertension artérielle")
    print(f"  dim={len(v)} first3={v[:3]}")
    print()
    print("OK — local stack working.")


if __name__ == "__main__":
    asyncio.run(main())
