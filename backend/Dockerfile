FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN python -m spacy download fr_core_news_md || true

# Pre-cache ML model weights so cold-starts don't depend on HF network.
# Each block is best-effort — the app falls back if a model is missing.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3', device='cpu')" || true
RUN python -c "from transformers import pipeline; pipeline('token-classification', model='Jean-Baptiste/camembert-ner', aggregation_strategy='simple', device=-1)" || true
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" || true

COPY app ./app
COPY data ./data
COPY scripts ./scripts
COPY tests ./tests
COPY pytest.ini ./pytest.ini

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
