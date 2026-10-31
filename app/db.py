"""Postgres + pgvector storage, and the ingest job table."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .config import DATABASE_URL, EMBED_DIM

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS docs (
    id          bigserial primary key,
    source      text,
    chunk_index int,
    text        text,
    embedding   vector({EMBED_DIM}),
    meta        jsonb,
    unique(source, chunk_index)
);

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id         uuid primary key,
    status     text not null,
    request    jsonb not null,
    chunks     int default 0,
    error      text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS docs_embedding_idx ON docs USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS docs_fts_idx ON docs USING gin (to_tsvector('english', text));
CREATE INDEX IF NOT EXISTS docs_source_idx ON docs (source);
"""


def vector_literal(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


class Database:
    def __init__(self, dsn: str = DATABASE_URL):
        self.dsn = dsn
        self.conn: psycopg.Connection | None = None

    def connect(self) -> "Database":
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True)
        return self

    def close(self) -> None:
        if self.conn and not self.conn.closed:
            self.conn.close()

    def init_schema(self) -> None:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute(INDEXES)

    # ---------------------------------------------------------------- docs
    def truncate_docs(self) -> None:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE docs RESTART IDENTITY")

    def count_docs(self) -> int:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM docs")
            return int(cur.fetchone()["n"])

    def insert_chunks(self, rows: list[dict]) -> int:
        self.connect()
        payload = [
            (
                row["source"],
                row["chunk_index"],
                row["text"],
                vector_literal(row["embedding"]),
                json.dumps(row.get("meta", {})),
            )
            for row in rows
        ]
        with self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO docs (source, chunk_index, text, embedding, meta)
                   VALUES (%s, %s, %s, %s::vector, %s::jsonb)
                   ON CONFLICT (source, chunk_index) DO UPDATE
                   SET text = excluded.text,
                       embedding = excluded.embedding,
                       meta = excluded.meta""",
                payload,
            )
        return len(payload)

    def vector_search(self, query_vector: list[float], k: int) -> list[dict]:
        self.connect()
        literal = vector_literal(query_vector)
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, source, chunk_index, text, meta,
                          1 - (embedding <=> %s::vector) AS score
                   FROM docs
                   ORDER BY embedding <=> %s::vector
                   LIMIT %s""",
                (literal, literal, k),
            )
            return cur.fetchall()

    def fts_search(self, query: str, k: int) -> list[dict]:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, source, chunk_index, text, meta,
                          ts_rank_cd(to_tsvector('english', text),
                                     websearch_to_tsquery('english', %s)) AS score
                   FROM docs
                   WHERE to_tsvector('english', text) @@ websearch_to_tsquery('english', %s)
                   ORDER BY score DESC, id
                   LIMIT %s""",
                (query, query, k),
            )
            return cur.fetchall()

    # ---------------------------------------------------------------- jobs
    def create_job(self, job_id: UUID, request: dict) -> None:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingest_jobs (id, status, request) VALUES (%s, 'queued', %s::jsonb)",
                (str(job_id), json.dumps(request)),
            )

    def update_job(self, job_id: UUID, status: str, chunks: int = 0, error: str | None = None) -> None:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE ingest_jobs
                   SET status = %s, chunks = %s, error = %s, updated_at = now()
                   WHERE id = %s""",
                (status, chunks, error, str(job_id)),
            )

    def get_job(self, job_id: UUID) -> dict | None:
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT id, status, chunks, error, created_at, updated_at, request
                   FROM ingest_jobs WHERE id = %s""",
                (str(job_id),),
            )
            return cur.fetchone()

    # ---------------------------------------------------------------- health
    def health(self) -> dict[str, Any]:
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cur.fetchone()
                cur.execute("SELECT count(*) AS n FROM docs")
                chunks = int(cur.fetchone()["n"])
            return {"reachable": True, "pgvector": row["extversion"] if row else None, "chunks": chunks}
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            return {"reachable": False, "error": str(exc)}
