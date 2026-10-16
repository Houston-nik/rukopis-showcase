"""Проверки файлов и адреса сервера. Наружу в сеть программа не открывается."""

from __future__ import annotations

from pathlib import Path

HOST = "127.0.0.1"
PORT = 8766
MAX_BYTES = 15 * 1024 * 1024
MAX_REQUEST_BYTES = 40 * 1024 * 1024
MAX_PHOTOS = 8

ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_TEXT = {".txt", ".md", ".pdf", ".docx"}


class SecurityError(Exception):
    pass


def assert_local_bind(host: str) -> str:
    if host != HOST:
        raise SecurityError("Сервер можно открыть только на этом компьютере")
    return host


def clean_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    if not base or base in {".", ".."} or "/" in base or "\\" in base:
        raise SecurityError("неправильное имя файла")
    return base


def check_upload(filename: str, data: bytes, kind: str) -> str:
    if kind == "image":
        allowed = ALLOWED_IMAGE
    elif kind == "text":
        allowed = ALLOWED_TEXT
    else:
        raise SecurityError("неизвестный тип загрузки")
    base = clean_filename(filename)
    ext = Path(base).suffix.lower()
    if ext not in allowed:
        raise SecurityError(
            "Такой файл нельзя. Картинки: png, jpg, webp. Текст: txt, md, pdf, docx."
        )
    if len(data) > MAX_BYTES:
        raise SecurityError("Файл больше 15 мегабайт")
    if len(data) == 0:
        raise SecurityError("Файл пустой")
    return ext


def safe_child(root: Path, name: str) -> Path:
    if name != Path(name).name or ".." in name or "/" in name or "\\" in name:
        raise SecurityError("путь выходит за папку программы")
    path = (root / name).resolve()
    root_resolved = root.resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise SecurityError("путь выходит за папку программы")
    return path
