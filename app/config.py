"""Configuration for the FastAPI service."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1:55432/rag_eval")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:7b")
EMBED_DIM = 768

CHUNK_TOKENS = 400
CHARS_PER_TOKEN = 4

TOP_K = 5
MAX_K = 20
HYBRID_CANDIDATES = 20
RRF_K = 60

TEMPERATURE = 0.0
NUM_CTX = 2048
MAX_PROMPT_CHUNK_CHARS = 900
KEEP_ALIVE = "30m"
REQUEST_TIMEOUT = 180

# /ingest may only read files under this directory.
INGEST_ALLOWED_ROOT = Path(os.environ.get("INGEST_ALLOWED_ROOT", ROOT / "sample_docs")).resolve()

APP_VERSION = "1.0.0"
