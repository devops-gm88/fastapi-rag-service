"""Heading-aware chunker for inbound documents."""
from __future__ import annotations

import re

from .config import CHARS_PER_TOKEN, CHUNK_TOKENS

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    para: list[str] = []
    for line in text.splitlines():
        heading = HEADING_RE.match(line.strip())
        if heading:
            if para:
                blocks.append(("para", " ".join(para).strip()))
                para = []
            blocks.append(("heading", f"{heading.group(1)} {heading.group(2).strip()}"))
        elif line.strip().startswith(("- ", "* ", "|")):
            if para:
                blocks.append(("para", " ".join(para).strip()))
                para = []
            blocks.append(("list", line.strip()))
        elif not line.strip():
            if para:
                blocks.append(("para", " ".join(para).strip()))
                para = []
        else:
            para.append(line.strip())
    if para:
        blocks.append(("para", " ".join(para).strip()))
    return [(kind, body) for kind, body in blocks if body]


def _split_long(body: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", body)
    parts: list[str] = []
    buffer = ""
    for sentence in sentences:
        if len(buffer) + len(sentence) + 1 > max_chars and buffer:
            parts.append(buffer.strip())
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        parts.append(buffer.strip())
    return parts


def chunk_text(title: str, text: str, max_tokens: int = CHUNK_TOKENS) -> list[str]:
    max_chars = max_tokens * CHARS_PER_TOKEN
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    heading_path = title

    def flush() -> None:
        nonlocal buffer, size
        if buffer:
            chunks.append("\n".join(buffer).strip())
            buffer = []
            size = 0

    for kind, body in _blocks(text):
        if kind == "heading":
            flush()
            heading_path = body.lstrip("# ").strip()
            piece = f"{title} > {heading_path}"
            buffer.append(piece)
            size += len(piece)
            continue
        for part in [body] if len(body) <= max_chars else _split_long(body, max_chars):
            if size + len(part) > max_chars:
                flush()
                buffer.append(f"{title} > {heading_path}")
                size = len(buffer[0])
            buffer.append(part)
            size += len(part) + 1
    flush()
    return chunks
