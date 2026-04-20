import httpx
import pytest
import respx

from app.core.llm_provider import CloudProvider, OllamaProvider


@pytest.mark.asyncio
@respx.mock
async def test_ollama_generate():
    route = respx.post("http://ollama:11434/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={"response": "salut", "prompt_eval_count": 3, "eval_count": 2},
        )
    )
    p = OllamaProvider("http://ollama:11434", "llama3.1:8b-instruct", "nomic-embed-text")
    r = await p.generate("bonjour", system="sys", max_tokens=10)
    assert route.called
    assert r.text == "salut"
    assert r.provider == "local"
    assert r.completion_tokens == 2


@pytest.mark.asyncio
@respx.mock
async def test_ollama_embed():
    respx.post("http://ollama:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )
    p = OllamaProvider("http://ollama:11434", "llama3.1:8b-instruct", "nomic-embed-text")
    v = await p.embed("texte")
    assert v == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
@respx.mock
async def test_cloud_generate_openai_compatible():
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "pong"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
        )
    )
    p = CloudProvider("https://api.example.com/v1", "sk-xxx", "gpt-4o-mini", "openai")
    r = await p.generate("ping")
    assert r.text == "pong"
    assert r.provider == "cloud"


@pytest.mark.asyncio
async def test_cloud_generate_requires_key():
    p = CloudProvider("https://api.example.com/v1", "", "gpt-4o-mini", "openai")
    with pytest.raises(RuntimeError, match="missing_api_key"):
        await p.generate("ping")


@pytest.mark.asyncio
async def test_cloud_embed_disabled():
    p = CloudProvider("https://api.example.com/v1", "sk-xxx", "gpt-4o-mini", "openai")
    with pytest.raises(NotImplementedError, match="cloud_embeddings_disabled_by_policy"):
        await p.embed("x")


@pytest.mark.asyncio
@respx.mock
async def test_connectivity_probe_offline():
    from types import SimpleNamespace

    from app.core.connectivity import ConnectivityProbe

    respx.head("https://1.1.1.1").mock(side_effect=httpx.ConnectError("x"))
    settings = SimpleNamespace(connectivity_probe_url="https://1.1.1.1", connectivity_probe_interval=60)
    probe = ConnectivityProbe(settings)
    assert await probe._probe_once() is False


@pytest.mark.asyncio
@respx.mock
async def test_connectivity_probe_online():
    from types import SimpleNamespace

    from app.core.connectivity import ConnectivityProbe

    respx.head("https://1.1.1.1").mock(return_value=httpx.Response(200))
    settings = SimpleNamespace(connectivity_probe_url="https://1.1.1.1", connectivity_probe_interval=60)
    probe = ConnectivityProbe(settings)
    assert await probe._probe_once() is True
