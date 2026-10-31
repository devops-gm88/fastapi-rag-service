"""FastAPI service: typed endpoints over the RAG pipeline.

    uvicorn app.main:app --reload

Endpoints:
    POST /ingest         queue a background ingest, returns a job id
    GET  /ingest/{id}    job status and chunk count
    POST /query          grounded answer with citations
    GET  /health         database and model reachability
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse

from .answering import answer_question
from .config import APP_VERSION, CHAT_MODEL
from .db import Database
from .embedding import Ollama, OllamaError
from .ingest import run_ingest
from .models import (
    Citation,
    ComponentHealth,
    HealthResponse,
    IngestAccepted,
    IngestJob,
    IngestRequest,
    QueryRequest,
    QueryResponse,
)
from .retrieval import retrieve

log = logging.getLogger("rag-service")

db = Database()
ollama = Ollama()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db.init_schema()
    except Exception as exc:  # noqa: BLE001 - /health reports the failure
        log.warning("schema init skipped: %s", exc)
    yield
    db.close()


app = FastAPI(
    title="RAG service",
    version=APP_VERSION,
    summary="Typed retrieval-augmented answering over private documents.",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    database = db.health()
    model = ollama.health()
    ok = bool(database.get("reachable")) and bool(model.get("reachable"))
    return HealthResponse(
        status="ok" if ok else "degraded",
        version=APP_VERSION,
        database=ComponentHealth(reachable=bool(database.get("reachable")), detail=database),
        model=ComponentHealth(reachable=bool(model.get("reachable")), detail=model),
    )


@app.post("/ingest", response_model=IngestAccepted, status_code=status.HTTP_202_ACCEPTED, tags=["ingest"])
def ingest(request: IngestRequest, background: BackgroundTasks) -> IngestAccepted:
    if not db.health().get("reachable"):
        raise HTTPException(status_code=503, detail="database unavailable")
    job_id = uuid4()
    db.create_job(job_id, request.model_dump(exclude_none=True))
    background.add_task(run_ingest, job_id, request.model_dump(exclude_none=True), db, ollama)
    return IngestAccepted(job_id=str(job_id))


@app.get("/ingest/{job_id}", response_model=IngestJob, tags=["ingest"])
def ingest_status(job_id: UUID) -> IngestJob:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestJob(
        job_id=str(job["id"]),
        status=job["status"],
        chunks=job["chunks"] or 0,
        error=job["error"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@app.post("/query", response_model=QueryResponse, tags=["query"])
def query(request: QueryRequest) -> QueryResponse:
    if not db.health().get("reachable"):
        raise HTTPException(status_code=503, detail="database unavailable")
    try:
        result = retrieve(db, ollama, request.question, k=request.k)
        answer = answer_question(ollama, request.question, result["chunks"])
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=f"model unavailable: {exc}") from exc

    citations = []
    for number in answer["cited"]:
        chunk = result["chunks"][number - 1]
        citations.append(
            Citation(
                n=number,
                source=chunk["source"],
                chunk_index=chunk["chunk_index"],
                score=round(float(chunk.get("rrf_score") or chunk.get("score") or 0), 6),
                snippet=" ".join(chunk["text"].split())[:280],
            )
        )
    return QueryResponse(
        answer=answer["answer"],
        citations=citations,
        retrieval_ms=result["retrieval_ms"],
        model=CHAT_MODEL,
        refused=answer["refused"],
    )
