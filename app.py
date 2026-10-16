"""Локальная страница. Слушает только этот компьютер."""

from __future__ import annotations

import json
import re
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from rukopis.atlas_store import load_atlas, load_manifest, save_atlas
from rukopis.extract import SheetError, extract_sheet
from rukopis.logutil import log_step
from rukopis.pdf_export import save_pdf
from rukopis.propisi import propisi_pdf
from rukopis.render import render_document
from rukopis.security import (
    HOST,
    MAX_PHOTOS,
    MAX_REQUEST_BYTES,
    PORT,
    SecurityError,
    assert_local_bind,
    check_upload,
    safe_child,
)
from rukopis.textin import TextReadError, lightly_compress, read_text_bytes

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
SAMPLES = ROOT / "samples"
OUTPUT = ROOT / "output"
ATLAS = ROOT / "atlas"
JOB_RE = re.compile(r"^[a-f0-9]{32}$")
GLYPH_RE = re.compile(r"^[0-9A-Fa-f]{4,6}$")
PAGE_RE = re.compile(r"^page-\d+\.png$")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/":
                self._send_path(WEB / "index.html", "text/html; charset=utf-8")
                return
            if path == "/app.js":
                self._send_path(WEB / "app.js", "text/javascript; charset=utf-8")
                return
            if path == "/propisi.pdf":
                dest = OUTPUT / "propisi.pdf"
                propisi_pdf(dest)
                log_step("propisi")
                self._send_path(dest, "application/pdf")
                return
            if path == "/api/atlas":
                self._send_json(200, _public_atlas())
                return
            if path.startswith("/glyph/"):
                self._send_glyph(path[len("/glyph/") :])
                return
            if path.startswith("/file/"):
                self._send_download(path)
                return
            self.send_error(404)
        except (SheetError, SecurityError, TextReadError, OSError) as exc:
            log_step("error", error=type(exc).__name__)
            self._send_json(400, {"ok": False, "message": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_json(413, {"ok": False, "message": "Слишком большой запрос"})
            return
        body = self.rfile.read(length)
        try:
            if path == "/api/samples":
                self._send_json(200, _accept_samples(body, self.headers.get("Content-Type", "")))
                return
            if path == "/api/render":
                self._send_json(200, _accept_render(body, self.headers.get("Content-Type", "")))
                return
            self.send_error(404)
        except (SheetError, SecurityError, TextReadError, OSError) as exc:
            log_step("error", error=type(exc).__name__)
            self._send_json(400, {"ok": False, "message": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        log_step("http", path=self.path[:100])

    def _send_json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_path(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_glyph(self, token: str) -> None:
        if not GLYPH_RE.fullmatch(token):
            self.send_error(404)
            return
        path = safe_child(ATLAS / "glyphs", f"{token.upper()}.png")
        self._send_path(path, "image/png")

    def _send_download(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 3 or parts[0] != "file":
            self.send_error(404)
            return
        job, name = parts[1], parts[2]
        if not JOB_RE.fullmatch(job):
            self.send_error(404)
            return
        if name != "conspect.pdf" and not PAGE_RE.fullmatch(name):
            self.send_error(404)
            return
        job_dir = safe_child(OUTPUT, job)
        file_path = safe_child(job_dir, name)
        content_type = "application/pdf" if name.endswith(".pdf") else "image/png"
        self._send_path(file_path, content_type)


def _accept_samples(body: bytes, content_type: str) -> dict:
    _fields, files = _parse_multipart(body, content_type)
    photos = [item for item in files if item[0] == "photo" and item[1]]
    if not photos:
        raise SheetError("Выбери фото заполненных прописей")
    if len(photos) > MAX_PHOTOS:
        raise SecurityError("За один раз можно не больше 8 фото")
    merged: dict[str, Image.Image] = {}
    empty: list[str] = []
    for _field, filename, data in photos:
        ext = check_upload(filename, data, "image")
        stored = SAMPLES / f"{uuid.uuid4().hex}{ext}"
        stored.write_bytes(data)
        log_step("upload-photo", ext=ext, bytes=len(data))
        with Image.open(stored) as image:
            sheet = extract_sheet(image.convert("RGB"))
        merged.update(sheet.glyphs)
        empty.extend(sheet.empty)
        log_step("extract", page=sheet.page_index, glyphs=len(sheet.glyphs), empty=len(sheet.empty))
    manifest = save_atlas(merged, empty, ATLAS)
    return {"ok": True, "glyphs": len(manifest["glyphs"]), "empty": manifest["empty"]}


def _accept_render(body: bytes, content_type: str) -> dict:
    fields, files = _parse_multipart(body, content_type)
    mode = fields.get("mode", "ready")
    text = fields.get("text", "").strip()
    for field, filename, data in files:
        if field != "material" or not filename:
            continue
        check_upload(filename, data, "text")
        text = read_text_bytes(filename, data).strip()
        log_step("upload-text", ext=Path(filename).suffix.lower(), bytes=len(data), chars=len(text))
    if not text:
        raise TextReadError("Нет текста. Вставь конспект или выбери файл.")
    if mode != "ready":
        text = lightly_compress(text)
    glyphs = load_atlas(ATLAS)
    if not glyphs:
        raise SheetError("Сначала загрузи фото прописей, чтобы появилась твоя азбука.")
    result = render_document(text, glyphs)
    job = uuid.uuid4().hex
    job_dir = OUTPUT / job
    job_dir.mkdir(parents=True, exist_ok=True)
    page_names: list[str] = []
    for index, image in enumerate(result.pages, start=1):
        name = f"page-{index}.png"
        image.save(job_dir / name, format="PNG")
        page_names.append(name)
    save_pdf(result.pages, job_dir / "conspect.pdf")
    log_step(
        "render",
        pages=len(result.pages),
        lines=result.line_count,
        graphs=result.graph_count,
        missing=len(result.missing),
        chars=len(text),
    )
    return {
        "ok": True,
        "job": job,
        "pages": page_names,
        "missing": result.missing,
        "pdf": "conspect.pdf",
    }


def _public_atlas() -> dict:
    manifest = load_manifest(ATLAS)
    glyphs = []
    for char, name in manifest.get("glyphs", {}).items():
        if isinstance(char, str) and isinstance(name, str):
            glyphs.append({"char": char, "file": Path(name).name})
    return {"ok": True, "glyphs": glyphs, "empty": manifest.get("empty", [])}


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], list[tuple[str, str, bytes]]]:
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
    if not match:
        raise SecurityError("Не получилось прочитать форму")
    boundary = (match.group(1) or match.group(2)).strip().encode("utf-8", "replace")
    fields: dict[str, str] = {}
    files: list[tuple[str, str, bytes]] = []
    for part in body.split(b"--" + boundary):
        if not part or part in {b"--", b"--\r\n"}:
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if part.endswith(b"--"):
            part = part[:-2]
            if part.endswith(b"\r\n"):
                part = part[:-2]
        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        header = header_blob.decode("utf-8", "replace")
        name_match = re.search(r'name="([^"]+)"', header)
        if not name_match:
            continue
        name = name_match.group(1)
        file_match = re.search(r'filename="([^"]*)"', header)
        if file_match is not None:
            files.append((name, file_match.group(1), data))
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def main() -> None:
    if sys.version_info < (3, 10):
        sys.exit("Нужен Python 3.10 или новее")
    host = assert_local_bind(HOST)
    OUTPUT.mkdir(exist_ok=True)
    SAMPLES.mkdir(exist_ok=True)
    ATLAS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((host, PORT), Handler)
    print(f"Открой в браузере: http://{host}:{PORT}/")
    print("Чтобы остановить, закрой это окно или нажми Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Остановлено")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
