"""Hybrid retrieval: pgvector cosine plus Postgres full-text, fused with RRF."""
from __future__ import annotations

import time

from .config import HYBRID_CANDIDATES, RRF_K, TOP_K
from .db import Database
from .embedding import Ollama


def fuse(lists: list[list[dict]], k: int = RRF_K, limit: int = TOP_K) -> list[dict]:
    scores: dict[int, float] = {}
    best: dict[int, dict] = {}
    for ranked in lists:
        for rank, row in enumerate(ranked, start=1):
            key = int(row["id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            best.setdefault(key, dict(row))
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    out: list[dict] = []
    for position, (key, score) in enumerate(ordered, start=1):
        row = dict(best[key])
        row["rrf_score"] = round(score, 6)
        row["rank"] = position
        out.append(row)
    return out


def retrieve(
    db: Database,
    ollama: Ollama,
    question: str,
    k: int = TOP_K,
    query_vector: list[float] | None = None,
) -> dict:
    started = time.perf_counter()
    vector = query_vector if query_vector is not None else ollama.embed_one(question)
    vector_rows = db.vector_search(vector, max(k, HYBRID_CANDIDATES))
    fts_rows = db.fts_search(question, HYBRID_CANDIDATES)
    chunks = fuse([vector_rows, fts_rows], limit=k)
    return {
        "chunks": chunks,
        "retrieval_ms": round((time.perf_counter() - started) * 1000, 1),
    }
