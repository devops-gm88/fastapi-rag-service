"""API contract tests. The model and the database are real, not mocked."""
from __future__ import annotations

import pytest

from tests.conftest import poll_job

ANSWERABLE = "How many vehicles are in the Acme Fleet pilot?"
UNANSWERABLE = "What is the Acme Fleet annual revenue?"


# --------------------------------------------------------------------- health


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["reachable"] is True
    assert body["model"]["reachable"] is True


def test_health_reports_pgvector(client):
    detail = client.get("/health").json()["database"]["detail"]
    assert detail["pgvector"] is not None
    assert detail["chunks"] > 0


def test_openapi_documents_every_endpoint(client):
    schema = client.get("/openapi.json").json()
    assert {"/ingest", "/query", "/health"} <= set(schema["paths"])
    assert schema["info"]["version"]
    component_schemas = schema["components"]["schemas"]
    for name in ("IngestRequest", "IngestAccepted", "QueryRequest", "QueryResponse", "Citation"):
        assert name in component_schemas


# ---------------------------------------------------------------------- query


def test_query_returns_the_response_schema(client):
    body = client.post("/query", json={"question": ANSWERABLE, "k": 3}).json()
    assert set(body) == {"answer", "citations", "retrieval_ms", "model", "refused"}
    assert isinstance(body["answer"], str) and body["answer"]
    assert isinstance(body["citations"], list)
    assert isinstance(body["retrieval_ms"], (int, float))
    assert body["model"] == "qwen2.5:7b"
    assert body["refused"] is False


def test_query_answers_from_the_seeded_database(client):
    body = client.post("/query", json={"question": ANSWERABLE}).json()
    assert "120" in body["answer"]


def test_query_citation_points_at_a_seeded_source(client):
    body = client.post("/query", json={"question": ANSWERABLE}).json()
    assert body["citations"], "the answer must cite at least one chunk"
    citation = body["citations"][0]
    assert citation["source"].endswith(".md")
    assert citation["n"] >= 1
    assert 0 <= citation["score"] <= 1
    assert citation["snippet"]


def test_query_refuses_when_the_sources_do_not_answer(client):
    body = client.post("/query", json={"question": UNANSWERABLE}).json()
    assert body["refused"] is True
    assert "NOT IN SOURCES" in body["answer"].upper()


def test_query_honours_k(client):
    body = client.post("/query", json={"question": ANSWERABLE, "k": 2}).json()
    assert len(body["citations"]) <= 2


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "hi"},
        {"question": ANSWERABLE, "k": 0},
        {"question": ANSWERABLE, "k": 99},
        {"question": "x" * 501},
    ],
)
def test_query_rejects_bad_input_with_422(client, payload):
    assert client.post("/query", json=payload).status_code == 422


def test_query_requires_a_json_body(client):
    assert client.post("/query").status_code == 422


# --------------------------------------------------------------------- ingest


def test_ingest_inline_documents_returns_a_job(client):
    response = client.post(
        "/ingest",
        json={"documents": [{"title": "depot_notes.md", "text": "Depot B holds 40 vehicles.\n\nDepot A holds 50 vehicles."}]},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert len(body["job_id"]) == 36


def test_ingest_background_job_completes_and_writes_chunks(client):
    response = client.post(
        "/ingest",
        json={"documents": [{"title": "yard_rules.md", "text": "A vehicle may idle for 45 minutes before an alert.\n\nThe yard closes at 22:00."}]},
    )
    job = poll_job(client, response.json()["job_id"])
    assert job["status"] == "done"
    assert job["chunks"] >= 1


def test_ingest_from_the_allowed_root(client):
    response = client.post("/ingest", json={"source_path": "fleet_overview.md"})
    job = poll_job(client, response.json()["job_id"])
    assert job["status"] == "done"
    assert job["chunks"] >= 1


def test_ingest_reports_an_error_for_a_path_outside_the_root(client):
    response = client.post("/ingest", json={"source_path": "../../etc/passwd"})
    job = poll_job(client, response.json()["job_id"])
    assert job["status"] == "error"
    assert "allowed ingest root" in (job["error"] or "")


def test_ingest_rejects_both_inputs_with_422(client):
    response = client.post(
        "/ingest",
        json={
            "source_path": "fleet_overview.md",
            "documents": [{"title": "x.md", "text": "y"}],
        },
    )
    assert response.status_code == 422


def test_ingest_rejects_no_input_with_422(client):
    assert client.post("/ingest", json={}).status_code == 422


def test_unknown_job_returns_404(client):
    assert client.get("/ingest/00000000-0000-0000-0000-000000000000").status_code == 404
