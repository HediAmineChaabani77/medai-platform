"""Tiny mock that mimics Ollama's HTTP API surface for local tests.

Endpoints:
  POST /api/generate    -> returns a canned JSON response. If the prompt asks
                          for a JSON object (UC1), returns a structured one.
                          If it asks for markdown sections (UC2), returns
                          those. Otherwise returns a short French sentence.
  POST /api/embeddings  -> returns a deterministic 768-dim vector derived
                          from the prompt text (no real semantics, but stable
                          so RAG tests are reproducible).
  GET  /api/tags        -> returns a fake model list so health probes pass.

Zero external dependencies. Uses the stdlib HTTP server.
"""
from __future__ import annotations

import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = 768


def embed(text: str) -> list[float]:
    # Deterministic pseudo-embedding: repeat SHA-256 until DIM floats reached.
    buf: list[int] = []
    seed = text.encode("utf-8")
    while len(buf) < DIM:
        seed = hashlib.sha256(seed).digest()
        buf.extend(seed)
    vec = [((b / 255.0) * 2.0) - 1.0 for b in buf[:DIM]]
    # Normalise
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


def canned_generation(prompt: str) -> str:
    low = prompt.lower()
    if "diagnoses" in low and "red_flags" in low:
        return json.dumps(
            {
                "diagnoses": [
                    {
                        "condition": "Hypothèse générique A",
                        "probability": 0.55,
                        "reasoning": "Cohérent avec les symptômes et le contexte [SRC1].",
                        "icd10": "R00",
                        "citations": ["SRC1"],
                    },
                    {
                        "condition": "Hypothèse générique B",
                        "probability": 0.25,
                        "reasoning": "Différentiel plausible [SRC2].",
                        "icd10": None,
                        "citations": ["SRC2"],
                    },
                ],
                "red_flags": ["Signal d'alerte mocké — fièvre persistante"],
            },
            ensure_ascii=False,
        )
    if "## " in prompt or "rédige le compte-rendu" in low:
        return (
            "## Motif\nInformation extraite du texte brut (mock).\n\n"
            "## Anamnèse\nNon renseigné.\n\n"
            "## Examen clinique\nNon renseigné.\n\n"
            "## Conclusion\nCompte-rendu généré par le mock LLM.\n\n"
            "## Plan de soins\nReprise du travail à J+7 (mock).\n"
        )
    if "alerte" in low or "prescription" in low:
        return "Explication mock: à surveiller. Sources: [SRC1]."
    return "Réponse mock pour tests."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default access log
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path.rstrip("/") == "/api/tags":
            self._json({"models": [{"name": "llama3.1:8b-instruct"}, {"name": "nomic-embed-text"}]})
        elif self.path.rstrip("/") in ("", "/", "/health"):
            self._json({"ok": True, "service": "mock-ollama"})
        else:
            self._json({"error": "not_found", "path": self.path}, status=404)

    def do_POST(self):
        data = self._body()
        path = self.path.rstrip("/")
        if path == "/api/generate":
            prompt = data.get("prompt", "")
            resp = canned_generation(prompt)
            self._json({
                "model": data.get("model", "mock"),
                "response": resp,
                "done": True,
                "prompt_eval_count": len(prompt.split()),
                "eval_count": len(resp.split()),
            })
        elif path == "/api/embeddings":
            text = data.get("prompt", "")
            self._json({"embedding": embed(text)})
        else:
            self._json({"error": "not_found", "path": path}, status=404)


def main():
    addr = ("0.0.0.0", 11434)
    print(f"mock-ollama listening on {addr[0]}:{addr[1]}", flush=True)
    ThreadingHTTPServer(addr, Handler).serve_forever()


if __name__ == "__main__":
    main()
