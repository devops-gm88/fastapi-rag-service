# FastAPI RAG service


A typed HTTP service around a retrieval-augmented answering pipeline: Pydantic contracts on every request and response, Postgres with pgvector, and an OpenAPI document served at /docs.

**No CI workflow in this repo.** The number is a documented run: pytest **34 tests, all passed** in 48 s (2026-10-31) against a real Postgres database and a real model

```bash
make test
```

A typed HTTP service around a retrieval-augmented answering pipeline. Postgres 16
with pgvector stores the chunks. Ollama serves the embedding model and the chat
model. Every request and response has a Pydantic model, and the OpenAPI document
is served at `/docs`.

## What was run and what was not

**Run on this machine, 2026-10-31:**

- `uvicorn app.main:app` started the service. All endpoints were called with `curl`
  and the responses are pasted below, verbatim.
- `pytest` ran **34 tests, all passed** (48 s) against a real Postgres database
  seeded with the four documents in `sample_docs/`.
- `GET /health` reported the database reachable, pgvector 0.8.0 loaded, and both
  Ollama models present.

**Not run:**

- **Docker is not installed on this machine.** The `Dockerfile` and
  `docker-compose.yml` are written and reviewed line by line. The container was
  not built or started.
- No load test and no deployment. The timings below are single requests on one
  laptop.

**Container files are included and reviewed; the service was verified locally with uvicorn and pytest.**

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ingest` | Accept a file path or inline documents. Runs as a background task. Returns a job id. |
| `GET` | `/ingest/{job_id}` | Job status: `queued`, `running`, `done` or `error`, plus chunk count. |
| `POST` | `/query` | Body `{question, k}`. Returns `{answer, citations[], retrieval_ms, model, refused}`. |
| `GET` | `/health` | Database reachable, pgvector version, model reachable, chunk count. |
| `GET` | `/docs` | OpenAPI UI. `/openapi.json` is the machine document. |

`POST /ingest` validates that the resolved path sits inside `INGEST_ALLOWED_ROOT`.
A path outside that root fails the job with a recorded error.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# Postgres 16 + pgvector, then:
export DATABASE_URL=postgresql://127.0.0.1:55432/rag_api
make db            # creates the database and the vector extension
make run           # uvicorn app.main:app --reload

# Ollama, in another shell:
ollama pull nomic-embed-text
ollama serve
```

The service creates its own tables on start-up: `docs` and `ingest_jobs`.

## Curl output

Every block below is the real response from this machine.

`GET /health`

```json
{"status":"ok","version":"1.0.0","database":{"reachable":true,"detail":{"reachable":true,"pgvector":"0.8.0","chunks":0}},"model":{"reachable":true,"detail":{"reachable":true,"embed_model":"nomic-embed-text","chat_model":"qwen2.5:7b","embed_model_present":true,"chat_model_present":true}}}
```

`POST /ingest`

```json
{"job_id":"4178e252-882d-4227-a63e-bd07dfe0698d","status":"queued","detail":"Ingest runs in the background. Poll GET /ingest/{job_id}."}
```

`GET /ingest/{job_id}`

```json
{"job_id":"502edc28-89b3-4824-8450-5a515737b2d9","status":"done","chunks":3,"error":null,"created_at":"2026-10-31T06:44:44.600912-04:00","updated_at":"2026-10-31T06:44:45.175115-04:00"}
```

`POST /query` with a question the documents answer

```json
{"answer":"The Acme Fleet pilot covers 120 vehicles across 3 depots. [1]","citations":[{"n":1,"source":"fleet_overview.md","chunk_index":0,"score":0.016393,"snippet":"fleet_overview > Acme Fleet telematics pilot The pilot covers 120 vehicles across 3 depots. The pilot started on 2026-09-01. The go-live date is 2026-11-15. The project owner is the operations director. The fleet manager signs off each depot."}],"retrieval_ms":695.6,"model":"qwen2.5:7b","refused":false}
```

`POST /query` with a question the documents cannot answer

```json
{"answer":"NOT IN SOURCES","citations":[],"retrieval_ms":170.6,"model":"qwen2.5:7b","refused":true}
```

`POST /query` with `k: 0` returns `HTTP 422`. `GET /docs` returns `HTTP 200`.

## Tests

```
34 passed, 1 warning in 48.07s
```

The suite covers:

- the response schema and every field type;
- a query against a seeded test database, with the answer checked for the fact;
- the refusal path, which must return `NOT IN SOURCES`;
- 422 responses on six bad payloads plus a missing body;
- a background ingest job that writes chunks, read back through the job endpoint;
- path-traversal refusal for `../../etc/passwd`;
- chunker, fusion, citation parser and path resolver unit tests.

```bash
make test        # needs Postgres and Ollama running
```

The tests talk to `TEST_DATABASE_URL` (default `rag_api_test`) and create it if it
is missing. Nothing is mocked.

## Docker

`Dockerfile` builds `python:3.12-slim`, installs `requirements.txt`, copies `app/`
and `sample_docs/`, runs as a non-root user, and declares a `HEALTHCHECK` on
`/health`.

`docker-compose.yml` runs two services: `app` and `db` (`pgvector/pgvector:pg16`),
with a named volume and a `pg_isready` health gate. The app reaches a host Ollama
through `host.docker.internal`.

```bash
make up      # docker compose up --build -d
make down    # docker compose down -v
```

## Layout

```
app/
  main.py         FastAPI app and routes
  models.py       Pydantic request and response models
  config.py       environment and tuning values
  db.py           schema, chunk writes, vector and full-text search, job table
  embedding.py    Ollama client
  extraction.py   markdown, HTML, text and PDF to text
  chunking.py     heading-aware chunker
  retrieval.py    vector + full-text with reciprocal rank fusion
  answering.py    prompt, citation parser, refusal token
  ingest.py       the background ingest job
sample_docs/      four Acme Fleet documents used by the demo and the tests
tests/            pytest suite
scripts/          local database helper
```

## Design notes

- **Hybrid retrieval.** Vector top-20 and full-text top-20 are fused with
  reciprocal rank fusion (k=60). Vector search misses exact identifiers; full-text
  search misses paraphrases. The companion eval measured this on a 57-document
  corpus and found no pass-count difference against vector-only, so the claim here
  is design rationale, not a measured win.
- **Refusal is a first-class result.** The prompt requires the exact token
  `NOT IN SOURCES`, and the response carries `refused: true`. A caller can route
  on that without parsing prose.
- **Citations are numbers.** The prompt numbers each source; the parser keeps only
  numbers that exist. The response maps each number back to source and chunk index.
- **Ingest is a job, not a request.** A large ingest would otherwise hold the
  connection. The job row is the record.

## Limits

- Single worker. The job runner uses in-process background tasks, so a restart
  loses a queued job. A production version would put the queue outside the process.
- No authentication and no rate limit.
- The retrieval quality is measured in the companion build,
  `rag-eval-demo`: 30 questions, recall@5, citation correctness, refusal accuracy.