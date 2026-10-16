"""Чтение файла с материалом и лёгкое ужимание. Облако не используется."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader

MAX_CHARS = 200_000
MAX_PDF_PAGES = 40


class TextReadError(Exception):
    pass


def read_text_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md"}:
        return _clip(data.decode("utf-8-sig"))
    if ext == ".pdf":
        reader = PdfReader(BytesIO(data))
        return _clip(_pages_text(reader))
    if ext == ".docx":
        document = Document(BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        return _clip("\n".join(parts))
    raise TextReadError("Этот тип файла я не читаю")


def lightly_compress(text: str) -> str:
    kept: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("график:"):
            kept.append(line)
            continue
        if line.startswith("#") or re.match(r"^\d+[\.\)]\s+\S", line):
            kept.append(line)
            continue
        if any(token in line for token in ("^", "_", "√", "=", "формул", "\\frac", "\\sqrt")):
            kept.append(line)
            continue
        if len(line) <= 160:
            kept.append(line)
    if kept:
        return "\n".join(kept)
    parts = re.split(r"(?<=[\.\!\?])\s+", text.strip())
    short = [part.strip() for part in parts[:12] if part.strip()]
    return "\n".join(short)


def _pages_text(reader: PdfReader) -> str:
    chunks: list[str] = []
    for index, page in enumerate(reader.pages):
        if index >= MAX_PDF_PAGES:
            break
        extracted = page.extract_text() or ""
        if extracted.strip():
            chunks.append(extracted)
    return "\n".join(chunks)


def _clip(text: str) -> str:
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS]
    return text
