from app.core.rag import Chunk, Retrieval, build_rag_prompt, chunk_text, tokenize


def test_chunk_text_preserves_header():
    chunks = chunk_text("alpha beta gamma delta " * 200, size_tokens=100, overlap=10, section_header="Intro")
    assert all(c.startswith("[Intro]") for c in chunks)
    assert len(chunks) >= 2


def test_chunk_text_short():
    chunks = chunk_text("one two three", size_tokens=10, overlap=2)
    assert chunks == ["one two three"]


def test_tokenize_accents():
    toks = tokenize("Hypertension à traiter — INR élevé")
    assert "hypertension" in toks and "élevé" in toks


def test_build_rag_prompt_citations():
    retrievals = [
        Retrieval(
            chunk=Chunk(id="doc:0:0", text="Metformine en première ligne.", metadata={"source": "Vidal", "section": "Indications"}),
            score=0.9,
        ),
        Retrieval(
            chunk=Chunk(id="doc:1:0", text="CI si DFG < 30.", metadata={"source": "Vidal", "section": "Contre-indications"}),
            score=0.8,
        ),
    ]
    prompt, citations = build_rag_prompt("Metformine et insuffisance rénale ?", retrievals)
    assert "[SRC1]" in prompt and "[SRC2]" in prompt
    assert "Vidal" in prompt
    assert len(citations) == 2
    assert citations[0]["id"] == "SRC1"
