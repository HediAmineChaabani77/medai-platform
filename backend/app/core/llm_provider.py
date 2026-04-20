from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        format: str | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class OllamaProvider(LLMProvider):
    """Local provider. Talks to Ollama's HTTP API. No network beyond localhost."""

    name = "local"

    def __init__(
        self,
        host: str,
        model: str,
        embed_model: str,
        client: httpx.AsyncClient | None = None,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self._client = client

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        # Generous timeout because small local GPUs (e.g. GTX 1650) may partially
        # offload a 3B-class model to CPU, pushing first-token latency past 60s.
        return httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)), True

    async def generate(self, prompt, system=None, max_tokens=512, temperature=0.2, format=None) -> LLMResponse:
        client, owned = self._get_client()
        try:
            payload: dict = {
                "model": self.model,
                "prompt": prompt,
                "system": system or "",
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            }
            if format:
                # Ollama supports format="json" or a JSON-schema dict for structured output.
                payload["format"] = format
            r = await client.post(f"{self.host}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
            return LLMResponse(
                text=data.get("response", ""),
                model=self.model,
                provider=self.name,
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
            )
        finally:
            if owned:
                await client.aclose()

    async def embed(self, text: str) -> list[float]:
        client, owned = self._get_client()
        try:
            r = await client.post(
                f"{self.host}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
            )
            r.raise_for_status()
            return r.json()["embedding"]
        finally:
            if owned:
                await client.aclose()


class CloudProvider(LLMProvider):
    """OpenAI-compatible provider. Accepts any base_url (OpenAI, Azure, Mistral, Anthropic-compatible gateways)."""

    name = "cloud"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        provider_label: str = "openai",
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider_label = provider_label
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=60.0), True

    async def generate(self, prompt, system=None, max_tokens=512, temperature=0.2, format=None) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("cloud_provider_missing_api_key")
        client, owned = self._get_client()
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            body: dict = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if format == "json":
                body["response_format"] = {"type": "json_object"}
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            return LLMResponse(
                text=data["choices"][0]["message"]["content"],
                model=self.model,
                provider=self.name,
                prompt_tokens=data.get("usage", {}).get("prompt_tokens"),
                completion_tokens=data.get("usage", {}).get("completion_tokens"),
            )
        finally:
            if owned:
                await client.aclose()

    async def embed(self, text: str) -> list[float]:
        # Forbidden by design. Embeddings MUST be local so RAG works offline.
        raise NotImplementedError("cloud_embeddings_disabled_by_policy")


def build_local_provider(settings) -> OllamaProvider:
    return OllamaProvider(
        host=settings.ollama_host,
        model=settings.llm_local_model,
        embed_model=settings.llm_embed_model,
    )


def build_cloud_provider(settings) -> CloudProvider:
    return CloudProvider(
        base_url=settings.llm_cloud_base_url,
        api_key=settings.llm_cloud_api_key,
        model=settings.llm_cloud_model,
        provider_label=settings.llm_cloud_provider,
    )
