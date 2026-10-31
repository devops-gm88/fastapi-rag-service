"""The ingest job: extract, chunk, embed, insert."""
from __future__ import annotations

from uuid import UUID

from .chunking import chunk_text
from .config import INGEST_ALLOWED_ROOT
from .db import Database
from .embedding import Ollama
from .extraction import extract_text, resolve_source_path


def collect_documents(request: dict) -> list[dict]:
    """Turn an IngestRequest dict into [{source, title, text, meta}]."""
    if request.get("source_path"):
        path = resolve_source_path(request["source_path"], INGEST_ALLOWED_ROOT)
        return [
            {
                "source": request["source_path"],
                "title": path.stem,
                "text": extract_text(path),
                "meta": {"origin": "file", "suffix": path.suffix},
            }
        ]
    documents = []
    for item in request.get("documents") or []:
        documents.append(
            {
                "source": item["title"],
                "title": item["title"],
                "text": item["text"],
                "meta": {"origin": "inline"},
            }
        )
    return documents


def build_rows(documents: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for document in documents:
        for index, chunk in enumerate(chunk_text(document["title"], document["text"])):
            rows.append(
                {
                    "source": document["source"],
                    "chunk_index": index,
                    "text": chunk,
                    "meta": {"title": document["title"], **document.get("meta", {})},
                }
            )
    return rows


def run_ingest(job_id: UUID, request: dict, db: Database, ollama: Ollama) -> None:
    """Run in the background. Records status in ingest_jobs."""
    try:
        db.update_job(job_id, "running")
        documents = collect_documents(request)
        rows = build_rows(documents)
        if not rows:
            db.update_job(job_id, "done", chunks=0, error="no chunks produced")
            return
        vectors = ollama.embed([row["text"] for row in rows])
        for row, vector in zip(rows, vectors, strict=True):
            row["embedding"] = vector
        inserted = db.insert_chunks(rows)
        db.update_job(job_id, "done", chunks=inserted)
    except Exception as exc:  # noqa: BLE001 - the failure is the job result
        db.update_job(job_id, "error", error=str(exc)[:500])
