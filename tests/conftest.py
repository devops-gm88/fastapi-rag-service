"""Test fixtures.

The suite runs against a real Postgres database with pgvector, because the
service under test is a database-backed retrieval service. The database name is
rag_api_test. It is created and seeded once per session.

Set TEST_DATABASE_URL to point somewhere else.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://127.0.0.1:55432/rag_api_test",
)
os.environ["DATABASE_URL"] = TEST_DSN
os.environ.setdefault("INGEST_ALLOWED_ROOT", str(ROOT / "sample_docs"))

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.chunking import chunk_text  # noqa: E402
from app.db import Database  # noqa: E402
from app.embedding import Ollama  # noqa: E402
from app.main import app  # noqa: E402


def ensure_database(dsn: str) -> None:
    """Create the test database when it does not exist."""
    name = dsn.rsplit("/", 1)[-1]
    maintenance = dsn.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(maintenance, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session")
def client() -> TestClient:
    ensure_database(TEST_DSN)
    db = Database(TEST_DSN).connect()
    db.init_schema()
    db.truncate_docs()

    ollama = Ollama()
    rows: list[dict] = []
    for path in sorted((ROOT / "sample_docs").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for index, chunk in enumerate(chunk_text(path.stem, text)):
            rows.append(
                {
                    "source": path.name,
                    "chunk_index": index,
                    "text": chunk,
                    "meta": {"title": path.stem},
                }
            )
    vectors = ollama.embed([row["text"] for row in rows])
    for row, vector in zip(rows, vectors, strict=True):
        row["embedding"] = vector
    db.insert_chunks(rows)
    db.close()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def seeded_chunks(client) -> int:
    db = Database(TEST_DSN).connect()
    count = db.count_docs()
    db.close()
    return count


def poll_job(client: TestClient, job_id: str, attempts: int = 20) -> dict:
    import time

    for _ in range(attempts):
        response = client.get(f"/ingest/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"done", "error"}:
            return body
        time.sleep(0.2)
    raise AssertionError("ingest job did not finish")
