"""Размеры листа, клетки прописей и список знаков. Картинки здесь не рисуются."""

from __future__ import annotations

from dataclasses import dataclass

PAGE_W = 1240
PAGE_H = 1754
MARKER = 46
INSET = 28

COLS = 6
ROWS = 8
CELL = 168
GAP = 14
GRID_LEFT = 80
GRID_TOP = 150

PAGE_ID_X = 520
PAGE_ID_Y = 42
PAGE_ID_SIZE = 26
PAGE_ID_STEP = 40
PAGE_ID_BITS = 3

UPPER = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
LOWER = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
DIGITS = "0123456789"
SIGNS = "+−=()/^√-.,:;!?%*"
LATIN_LOWER = "abcdefghijklmnopqrstuvwxyz"
LATIN_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

ALL_CHARS = list(UPPER + LOWER + DIGITS + SIGNS + LATIN_LOWER + LATIN_UPPER)

REQUIRED_ON_SHEET = set(UPPER + LOWER + DIGITS + "+−=()/^√")


@dataclass(frozen=True)
class Cell:
    char: str
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class PageLayout:
    index: int
    cells: tuple[Cell, ...]


def marker_boxes() -> list[tuple[int, int, int, int]]:
    size = MARKER
    left = INSET
    right = PAGE_W - INSET - size
    top = INSET
    bottom = PAGE_H - INSET - size
    return [
        (left, top, size, size),
        (right, top, size, size),
        (left, bottom, size, size),
        (right, bottom, size, size),
    ]


def marker_centers() -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for x, y, w, h in marker_boxes():
        centers.append((x + w / 2.0, y + h / 2.0))
    return centers


def page_id_square(bit: int) -> tuple[int, int, int, int]:
    x = PAGE_ID_X + bit * PAGE_ID_STEP
    return (x, PAGE_ID_Y, PAGE_ID_SIZE, PAGE_ID_SIZE)


def build_pages() -> list[PageLayout]:
    per_page = COLS * ROWS
    pages: list[PageLayout] = []
    for start in range(0, len(ALL_CHARS), per_page):
        chunk = ALL_CHARS[start : start + per_page]
        cells: list[Cell] = []
        for number, char in enumerate(chunk):
            row = number // COLS
            col = number % COLS
            x = GRID_LEFT + col * (CELL + GAP)
            y = GRID_TOP + row * (CELL + GAP)
            cells.append(Cell(char, x, y, CELL, CELL))
        pages.append(PageLayout(start // per_page, tuple(cells)))
    return pages


def chars_on_sheets() -> set[str]:
    found: set[str] = set()
    for page in build_pages():
        for cell in page.cells:
            found.add(cell.char)
    return found
