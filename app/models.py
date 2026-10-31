"""Pydantic request and response models. Every endpoint is typed."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .config import MAX_K


class DocumentInput(BaseModel):
    title: str = Field(min_length=1, max_length=200, examples=["fleet_overview.md"])
    text: str = Field(min_length=1, max_length=200_000, examples=["The pilot covers 120 vehicles."])


class IngestRequest(BaseModel):
    """Send exactly one of source_path or documents."""

    source_path: str | None = Field(
        default=None,
        max_length=500,
        description="Path relative to INGEST_ALLOWED_ROOT. One file.",
        examples=["fleet_overview.md"],
    )
    documents: list[DocumentInput] | None = Field(
        default=None,
        max_length=200,
        description="Inline documents. Use this when the files are not on the server.",
    )

    @model_validator(mode="after")
    def exactly_one_input(self) -> "IngestRequest":
        has_path = bool(self.source_path)
        has_docs = bool(self.documents)
        if has_path == has_docs:
            raise ValueError("provide exactly one of source_path or documents")
        return self


class IngestAccepted(BaseModel):
    job_id: str = Field(examples=["8f14e45f-ceea-467f-a8b5-2c1f8b5f9a11"])
    status: Literal["queued"] = "queued"
    detail: str = "Ingest runs in the background. Poll GET /ingest/{job_id}."


class IngestJob(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    chunks: int = 0
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["How many vehicles are in the pilot?"])
    k: int = Field(default=5, ge=1, le=MAX_K, description=f"Chunks to retrieve, 1-{MAX_K}.")


class Citation(BaseModel):
    n: int = Field(ge=1, description="The number used in the answer text, for example [2].")
    source: str
    chunk_index: int
    score: float
    snippet: str = Field(max_length=280)


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval_ms: float
    model: str
    refused: bool = Field(description="True when the answer is NOT IN SOURCES.")


class ComponentHealth(BaseModel):
    reachable: bool
    detail: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: ComponentHealth
    model: ComponentHealth
