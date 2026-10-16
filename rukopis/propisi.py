"""Печать листов-прописей: серая буква в клетке и чёрные метки по углам."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from rukopis.layout import (
    PAGE_H,
    PAGE_ID_BITS,
    PAGE_W,
    Cell,
    PageLayout,
    build_pages,
    marker_boxes,
    page_id_square,
)
from rukopis.pdf_export import save_pdf

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\times.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)


class PropisiError(Exception):
    pass


def font_file() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise PropisiError(
        "Не нашёл шрифт (Arial, DejaVu Sans или Liberation Sans). Он нужен только для серых подсказок в клетках."
    )


@lru_cache(maxsize=32)
def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_file(), size)


def fit_font(draw: ImageDraw.ImageDraw, char: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    size = 96
    chosen = load_font(size)
    while size > 22:
        chosen = load_font(size)
        box = draw.textbbox((0, 0), char, font=chosen)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            return chosen
        size -= 4
    return chosen


def draw_page(layout: PageLayout) -> Image.Image:
    image = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for x, y, w, h in marker_boxes():
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=(0, 0, 0))
    for bit in range(PAGE_ID_BITS):
        x, y, w, h = page_id_square(bit)
        filled = bool(layout.index & (1 << bit))
        color = (0, 0, 0) if filled else (255, 255, 255)
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=color, outline=(0, 0, 0), width=2)
    label_font = load_font(28)
    draw.text((760, 40), f"Лист {layout.index + 1}", fill=(170, 170, 170), font=label_font)
    for cell in layout.cells:
        _draw_cell(draw, cell)
    return image


def _draw_cell(draw: ImageDraw.ImageDraw, cell: Cell) -> None:
    x, y, w, h = cell.x, cell.y, cell.w, cell.h
    draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(214, 218, 224), width=2)
    font = fit_font(draw, cell.char, w - 36, h - 36)
    box = draw.textbbox((0, 0), cell.char, font=font)
    text_w = box[2] - box[0]
    text_h = box[3] - box[1]
    text_x = x + (w - text_w) / 2 - box[0]
    text_y = y + (h - text_h) / 2 - box[1]
    draw.text((text_x, text_y), cell.char, fill=(198, 198, 198), font=font)


def build_propisi_images() -> list[tuple[PageLayout, Image.Image]]:
    pages = build_pages()
    return [(layout, draw_page(layout)) for layout in pages]


def propisi_pdf(dest: Path) -> Path:
    images = [image for _layout, image in build_propisi_images()]
    save_pdf(images, dest)
    return dest
