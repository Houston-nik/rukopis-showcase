"""Набор страницы тетради своими буквами, формулами и графиками."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from rukopis.formula import render_formula
from rukopis.graph import GraphError, parse_graph_line, render_graph
from rukopis.layout import PAGE_H, PAGE_W
from rukopis.propisi import load_font

MARGIN_L = 96
MARGIN_R = 70
MARGIN_T = 90
MARGIN_B = 90
LINE_GAP = 16
GLYPH_H = 36
CONTENT_WIDTH = PAGE_W - MARGIN_L - MARGIN_R
CONTENT_BOTTOM = PAGE_H - MARGIN_B
MAX_PAGES = 30
HEADING_RE = re.compile(r"^\d+[\.\)]\s+\S")


@dataclass
class RenderResult:
    pages: list[Image.Image]
    missing: list[str] = field(default_factory=list)
    line_count: int = 0
    line_widths: list[int] = field(default_factory=list)
    content_width: int = CONTENT_WIDTH
    graph_count: int = 0


class _Sheet:
    def __init__(self) -> None:
        self.page = _new_paper()
        self.draw = ImageDraw.Draw(self.page)
        self.y = MARGIN_T
        self.missing: list[str] = []


def render_document(text: str, glyphs: dict[str, Image.Image]) -> RenderResult:
    result = RenderResult(pages=[])
    sheet = _Sheet()

    def break_page() -> None:
        if len(result.pages) >= MAX_PAGES:
            return
        _footer(sheet)
        result.pages.append(sheet.page)
        sheet.page = _new_paper()
        sheet.draw = ImageDraw.Draw(sheet.page)
        sheet.y = MARGIN_T
        sheet.missing = []

    for raw_line in text.splitlines():
        if len(result.pages) >= MAX_PAGES:
            break
        line = raw_line.strip()
        if not line:
            sheet.y += 12
            continue
        if line.lower().startswith("график:"):
            if _place_graph(line, sheet, result, break_page):
                continue
            line = "График не нарисован."
        for sprite, width, heading, missing in _wrap_line(line, glyphs, result.content_width):
            if len(result.pages) >= MAX_PAGES:
                break
            sheet.missing.extend(missing)
            result.missing.extend(missing)
            if sheet.y + sprite.height + LINE_GAP > CONTENT_BOTTOM:
                break_page()
            if heading:
                sheet.draw.rectangle(
                    (MARGIN_L - 6, sheet.y - 2, MARGIN_L + width + 8, sheet.y + sprite.height + 4),
                    fill=(255, 198, 216),
                )
            sheet.page.paste(sprite, (MARGIN_L, sheet.y), sprite)
            result.line_count += 1
            result.line_widths.append(width)
            sheet.y += sprite.height + LINE_GAP
    if len(result.pages) < MAX_PAGES:
        _footer(sheet)
        result.pages.append(sheet.page)
    result.missing = _unique(result.missing)
    return result


def _place_graph(line: str, sheet: _Sheet, result: RenderResult, break_page) -> bool:
    try:
        spec = parse_graph_line(line)
        if spec is None:
            return False
        graph = render_graph(spec)
    except GraphError:
        return False
    scaled = _fit_width(graph, result.content_width)
    if sheet.y + scaled.height + LINE_GAP > CONTENT_BOTTOM:
        break_page()
    sheet.page.paste(scaled, (MARGIN_L, sheet.y))
    result.graph_count += 1
    result.line_count += 1
    result.line_widths.append(scaled.width)
    sheet.y += scaled.height + LINE_GAP
    return True


def _wrap_line(
    line: str,
    glyphs: dict[str, Image.Image],
    max_width: int,
) -> list[tuple[Image.Image, int, bool, list[str]]]:
    heading = line.startswith("#") or bool(HEADING_RE.match(line))
    shown = line[1:].strip() if line.startswith("#") else line
    words = shown.split()
    if not words:
        return []
    rows: list[tuple[Image.Image, int, bool, list[str]]] = []
    current: list[Image.Image] = []
    current_missing: list[str] = []
    current_width = 0
    space = 12
    for word in words:
        sprite, missing = render_formula(word, glyphs, GLYPH_H)
        extra = sprite.width if not current else sprite.width + space
        if current and current_width + extra > max_width:
            rows.append((*_join(current, space), heading, list(current_missing)))
            current = [sprite]
            current_missing = list(missing)
            current_width = sprite.width
        else:
            current.append(sprite)
            current_missing.extend(missing)
            current_width += extra
    if current:
        rows.append((*_join(current, space), heading, current_missing))
    return rows


def _join(sprites: list[Image.Image], space: int) -> tuple[Image.Image, int]:
    height = max(sprite.height for sprite in sprites)
    width = sum(sprite.width for sprite in sprites) + space * (len(sprites) - 1)
    canvas = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    x_pos = 0
    for sprite in sprites:
        y_pos = height - sprite.height
        canvas.paste(sprite, (x_pos, y_pos), sprite)
        x_pos += sprite.width + space
    return canvas, width


def _fit_width(image: Image.Image, max_width: int) -> Image.Image:
    if image.width <= max_width:
        return image
    new_h = max(1, int(image.height * max_width / image.width))
    return image.resize((max_width, new_h), Image.Resampling.LANCZOS)


def _new_paper() -> Image.Image:
    image = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for y_pos in range(110, PAGE_H - 36, 46):
        draw.line((54, y_pos, PAGE_W - 36, y_pos), fill=(176, 208, 236), width=1)
    draw.line((68, 48, 68, PAGE_H - 36), fill=(232, 170, 170), width=2)
    return image


def _footer(sheet: _Sheet) -> None:
    missing = _unique(sheet.missing)
    if not missing:
        return
    font = load_font(22)
    shown = " ".join(missing[:24])
    sheet.draw.text((MARGIN_L, PAGE_H - 58), f"Допиши в пропись: {shown}", fill=(140, 90, 20), font=font)


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
