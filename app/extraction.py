"""Document text extraction: markdown, HTML, plain text and PDF."""
from __future__ import annotations

import html as htmllib
import re
from pathlib import Path

SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf"}


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)

    def heading(match: re.Match) -> str:
        level = int(match.group(1))
        body = re.sub(r"(?s)<[^>]+>", " ", match.group(2)).strip()
        return f"\n\n{'#' * level} {body}\n\n" if body else "\n"

    raw = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", heading, raw)
    raw = re.sub(r"(?i)<li[^>]*>", "\n- ", raw)
    raw = re.sub(r"(?i)</(p|li|tr|div|section|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = htmllib.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def pdf_to_text(path: Path) -> str:
    from pypdf import PdfReader

    pages = [(page.extract_text() or "") for page in PdfReader(str(path)).pages]
    text = "\n\n".join(pages)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return pdf_to_text(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        return html_to_text(raw)
    return raw.strip()


def resolve_source_path(source_path: str, allowed_root: Path) -> Path:
    """Resolve a source path and refuse anything outside the allowed root."""
    candidate = (allowed_root / source_path).resolve()
    if not str(candidate).startswith(str(allowed_root)):
        raise PermissionError(f"path outside the allowed ingest root: {source_path}")
    if not candidate.is_file():
        raise FileNotFoundError(source_path)
    if candidate.suffix.lower() not in SUFFIXES:
        raise ValueError(f"unsupported file type: {candidate.suffix}")
    return candidate
