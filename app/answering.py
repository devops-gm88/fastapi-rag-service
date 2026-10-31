"""Grounded answer generation with a mandatory citation and a refusal token."""
from __future__ import annotations

import re

from .config import MAX_PROMPT_CHUNK_CHARS
from .embedding import Ollama

REFUSAL = "NOT IN SOURCES"

SYSTEM = (
    "You answer questions about a private document set. "
    "You never invent facts and you never use outside knowledge."
)

PROMPT = """Answer the question from the sources below.

Rules:
1. Put the source number in square brackets after every claim, for example [2].
2. If the sources do not contain the answer, reply exactly: NOT IN SOURCES
3. Use only the sources. Do not add outside knowledge.
4. Answer in one to three sentences.

{sources}

QUESTION: {question}

ANSWER:"""


def build_prompt(question: str, chunks: list[dict]) -> str:
    parts = []
    for position, chunk in enumerate(chunks, start=1):
        title = (chunk.get("meta") or {}).get("title", chunk.get("source", ""))
        parts.append(f"SOURCE {position} (title: {title})\n{chunk['text'][:MAX_PROMPT_CHUNK_CHARS]}")
    return PROMPT.format(sources="\n\n".join(parts), question=question)


def parse_citations(answer: str, chunk_count: int) -> list[int]:
    ids = {int(value) for value in re.findall(r"\[(\d{1,2})\]", answer)}
    return sorted(value for value in ids if 1 <= value <= chunk_count)


def is_refusal(answer: str) -> bool:
    return REFUSAL in answer.upper()


def answer_question(ollama: Ollama, question: str, chunks: list[dict]) -> dict:
    answer = ollama.chat(build_prompt(question, chunks), SYSTEM)
    return {
        "answer": answer,
        "refused": is_refusal(answer),
        "cited": parse_citations(answer, len(chunks)),
    }
