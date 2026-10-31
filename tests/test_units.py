"""Unit tests: chunking, fusion, citation parsing, path safety."""
from __future__ import annotations

import pytest

from app.answering import build_prompt, is_refusal, parse_citations
from app.chunking import chunk_text
from app.config import INGEST_ALLOWED_ROOT
from app.extraction import resolve_source_path
from app.retrieval import fuse


def test_chunk_text_keeps_the_heading_path_in_the_chunk():
    text = "# Overview\n\nThe pilot covers 120 vehicles.\n\n## Scope\n\nLive position every 15 minutes."
    chunks = chunk_text("fleet_overview", text)
    assert chunks
    assert all(chunk.startswith("fleet_overview") for chunk in chunks)
    assert any("Scope" in chunk for chunk in chunks)


def test_chunk_text_splits_long_text():
    paragraph = "The vehicle reports its position. " * 200
    chunks = chunk_text("long", paragraph, max_tokens=100)
    assert len(chunks) > 1
    assert all(len(chunk) <= 100 * 4 + 200 for chunk in chunks)


def test_chunk_text_keeps_short_text_in_one_chunk():
    chunks = chunk_text("short", "One sentence only.")
    assert len(chunks) == 1


def test_fuse_ranks_a_row_found_by_both_lists_first():
    vector_rows = [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}]
    fts_rows = [{"id": 2, "text": "b"}, {"id": 3, "text": "c"}]
    fused = fuse([vector_rows, fts_rows], limit=3)
    assert fused[0]["id"] == 2
    assert {row["id"] for row in fused} == {1, 2, 3}


def test_fuse_returns_at_most_limit_rows():
    rows = [{"id": index, "text": "x"} for index in range(10)]
    assert len(fuse([rows], limit=4)) == 4


def test_parse_citations_drops_invalid_numbers():
    assert parse_citations("Answer [1] and [4] and [9].", chunk_count=3) == [1]


def test_parse_citations_ignores_plain_brackets():
    assert parse_citations("No citations [source] here.", chunk_count=3) == []


def test_is_refusal_is_case_insensitive():
    assert is_refusal("not in sources")
    assert not is_refusal("The answer is 120 vehicles [1].")


def test_build_prompt_numbers_every_source():
    chunks = [
        {"text": "first", "meta": {"title": "one"}},
        {"text": "second", "meta": {"title": "two"}},
    ]
    prompt = build_prompt("How many?", chunks)
    assert "SOURCE 1" in prompt and "SOURCE 2" in prompt
    assert "How many?" in prompt


def test_resolve_source_path_rejects_traversal():
    with pytest.raises(PermissionError):
        resolve_source_path("../../etc/passwd", INGEST_ALLOWED_ROOT)


def test_resolve_source_path_accepts_a_sample_document():
    resolved = resolve_source_path("fleet_overview.md", INGEST_ALLOWED_ROOT)
    assert resolved.is_file()


def test_resolve_source_path_rejects_unknown_suffix(tmp_path, monkeypatch):
    bad = tmp_path / "notes.exe"
    bad.write_text("x")
    with pytest.raises(ValueError):
        resolve_source_path("notes.exe", tmp_path)
