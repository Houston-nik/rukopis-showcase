"""PDF из готовых страниц. Число страниц потом сверяется отдельно."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def save_pdf(images: list[Image.Image], dest: Path) -> None:
    if not images:
        raise ValueError("нет страниц для PDF")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgb = [image.convert("RGB") for image in images]
    rgb[0].save(
        dest,
        format="PDF",
        save_all=True,
        append_images=rgb[1:],
        resolution=150.0,
        title="Рукописный конспект",
    )
