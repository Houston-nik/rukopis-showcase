"""Сохранение азбуки почерка на диск. В журнал сам текст конспекта не попадает."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from rukopis.logutil import log_step


def save_atlas(glyphs: dict[str, Image.Image], empty: list[str], dest: Path, log_path: Path | None = None) -> dict:
    glyph_dir = dest / "glyphs"
    glyph_dir.mkdir(parents=True, exist_ok=True)
    for old in glyph_dir.glob("*.png"):
        old.unlink()
    stored: dict[str, str] = {}
    for char, image in glyphs.items():
        name = f"{ord(char):04X}.png"
        image.save(glyph_dir / name, format="PNG")
        stored[char] = name
    manifest = {
        "glyphs": stored,
        "empty": [char for char in empty if char not in glyphs],
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log_step("atlas", log_path=log_path, glyphs=len(stored), empty=len(manifest["empty"]))
    return manifest


def load_atlas(dest: Path) -> dict[str, Image.Image]:
    manifest_path = dest / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    glyphs: dict[str, Image.Image] = {}
    for char, name in manifest.get("glyphs", {}).items():
        if not isinstance(char, str) or len(char) != 1:
            continue
        if not isinstance(name, str) or Path(name).name != name:
            continue
        path = dest / "glyphs" / name
        if path.is_file():
            glyphs[char] = Image.open(path).convert("RGBA")
    return glyphs


def load_manifest(dest: Path) -> dict:
    path = dest / "manifest.json"
    if not path.is_file():
        return {"glyphs": {}, "empty": []}
    return json.loads(path.read_text(encoding="utf-8"))
