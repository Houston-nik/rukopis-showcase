"""Выравнивание фото по чёрным меткам и нарезка клеток с буквами."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from rukopis.layout import (
    PAGE_H,
    PAGE_ID_BITS,
    PAGE_W,
    Cell,
    PageLayout,
    build_pages,
    marker_centers,
    page_id_square,
)
from rukopis.propisi import build_propisi_images

CORNER_FRACTION = 0.32
DARK_MARKER = 50
INK_MAX = 110
MIN_INK_PIXELS = 40


class SheetError(Exception):
    pass


@dataclass
class ExtractedSheet:
    page_index: int
    glyphs: dict[str, Image.Image]
    empty: list[str]


def limit_size(image: Image.Image, max_side: int = 1800) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)


def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> np.ndarray:
    matrix_rows: list[list[float]] = []
    targets: list[float] = []
    for (x_coord, y_coord), (u_coord, v_coord) in zip(src, dst):
        matrix_rows.append([x_coord, y_coord, 1, 0, 0, 0, -u_coord * x_coord, -u_coord * y_coord])
        matrix_rows.append([0, 0, 0, x_coord, y_coord, 1, -v_coord * x_coord, -v_coord * y_coord])
        targets.append(u_coord)
        targets.append(v_coord)
    solved = np.linalg.solve(np.asarray(matrix_rows, dtype=np.float64), np.asarray(targets, dtype=np.float64))
    return np.array(
        [
            [solved[0], solved[1], solved[2]],
            [solved[3], solved[4], solved[5]],
            [solved[6], solved[7], 1.0],
        ],
        dtype=np.float64,
    )


def resample_nearest(
    source: Image.Image,
    matrix_dst_from_src: np.ndarray,
    out_size: tuple[int, int],
    background: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    inverse = np.linalg.inv(matrix_dst_from_src)
    out_w, out_h = out_size
    pixels = np.asarray(source.convert("RGB"))
    src_h, src_w = pixels.shape[:2]
    ys, xs = np.indices((out_h, out_w))
    x_coord = xs.astype(np.float32) + 0.5
    y_coord = ys.astype(np.float32) + 0.5
    row0 = inverse[0]
    row1 = inverse[1]
    row2 = inverse[2]
    weight = row2[0] * x_coord + row2[1] * y_coord + row2[2]
    src_x = (row0[0] * x_coord + row0[1] * y_coord + row0[2]) / weight - 0.5
    src_y = (row1[0] * x_coord + row1[1] * y_coord + row1[2]) / weight - 0.5
    nearest_x = np.rint(src_x).astype(np.int32)
    nearest_y = np.rint(src_y).astype(np.int32)
    valid = (
        (nearest_x >= 0)
        & (nearest_y >= 0)
        & (nearest_x < src_w)
        & (nearest_y < src_h)
        & np.isfinite(weight)
        & (np.abs(weight) > 1e-6)
    )
    output = np.empty((out_h, out_w, 3), dtype=np.uint8)
    output[..., 0] = background[0]
    output[..., 1] = background[1]
    output[..., 2] = background[2]
    output[valid] = pixels[nearest_y[valid], nearest_x[valid]]
    return Image.fromarray(output)


def find_marker_centers(photo: Image.Image) -> list[tuple[float, float]]:
    gray = np.asarray(photo.convert("L"))
    height, width = gray.shape
    win_w = max(20, int(width * CORNER_FRACTION))
    win_h = max(20, int(height * CORNER_FRACTION))
    windows = [
        (0, 0, win_w, win_h),
        (width - win_w, 0, width, win_h),
        (0, height - win_h, win_w, height),
        (width - win_w, height - win_h, width, height),
    ]
    centers: list[tuple[float, float]] = []
    for x0, y0, x1, y1 in windows:
        center = _dark_centroid(gray, x0, y0, x1, y1)
        if center is None:
            raise SheetError(
                "Не вижу чёрные метки по углам. Сфотографируй лист целиком, чтобы все четыре угла попали в кадр."
            )
        centers.append(center)
    _ensure_spread(centers)
    return centers


def straighten(photo: Image.Image) -> Image.Image:
    limited = limit_size(photo)
    found = find_marker_centers(limited)
    matrix = homography(found, marker_centers())
    return resample_nearest(limited, matrix, (PAGE_W, PAGE_H))


def read_page_index(page: Image.Image) -> int:
    index = 0
    for bit in range(PAGE_ID_BITS):
        x, y, w, h = page_id_square(bit)
        pixel = page.getpixel((x + w // 2, y + h // 2))
        if isinstance(pixel, tuple):
            brightness = sum(pixel[:3]) / 3
        else:
            brightness = float(pixel)
        if brightness < 140:
            index |= 1 << bit
    return index


def extract_sheet(photo: Image.Image, layouts: list[PageLayout] | None = None) -> ExtractedSheet:
    pages = layouts or build_pages()
    straight = straighten(photo)
    index = read_page_index(straight)
    if index < 0 or index >= len(pages):
        raise SheetError("Не понял, какой это лист прописи. Нужны фото именно этих листов.")
    glyphs: dict[str, Image.Image] = {}
    empty: list[str] = []
    for cell in pages[index].cells:
        glyph = glyph_from_cell(straight, cell)
        if glyph is None:
            empty.append(cell.char)
        else:
            glyphs[cell.char] = glyph
    return ExtractedSheet(index, glyphs, empty)


def glyph_from_cell(page: Image.Image, cell: Cell) -> Image.Image | None:
    inset = 12
    crop = page.crop((cell.x + inset, cell.y + inset, cell.x + cell.w - inset, cell.y + cell.h - inset))
    pixels = np.asarray(crop.convert("RGB"))
    dark = pixels.min(axis=2) < INK_MAX
    if int(dark.sum()) < MIN_INK_PIXELS:
        return None
    ys, xs = np.nonzero(dark)
    pad = 2
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(pixels.shape[1], int(xs.max()) + 1 + pad)
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(pixels.shape[0], int(ys.max()) + 1 + pad)
    cut = pixels[y0:y1, x0:x1]
    mask = cut.min(axis=2) < INK_MAX
    rgba = np.zeros((cut.shape[0], cut.shape[1], 4), dtype=np.uint8)
    rgba[..., :3] = cut
    rgba[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def paint_control_ink(page: Image.Image, cells: tuple[Cell, ...], skip_char: str | None = None) -> Image.Image:
    painted = page.copy()
    draw = ImageDraw.Draw(painted)
    for cell in cells:
        if cell.char == skip_char:
            continue
        x, y, w, h = cell.x, cell.y, cell.w, cell.h
        draw.rectangle((x + 36, y + h // 2 - 8, x + w - 36, y + h // 2 + 8), fill=(15, 35, 120))
    return painted


def skew_photo(page: Image.Image) -> Image.Image:
    source_centers = marker_centers()
    destination = [
        (source_centers[0][0] + 36, source_centers[0][1] + 28),
        (source_centers[1][0] + 70, source_centers[1][1] + 48),
        (source_centers[2][0] + 24, source_centers[2][1] + 90),
        (source_centers[3][0] + 96, source_centers[3][1] + 120),
    ]
    out_w = int(max(point[0] for point in destination) + 70)
    out_h = int(max(point[1] for point in destination) + 70)
    matrix = homography(source_centers, destination)
    return resample_nearest(page, matrix, (out_w, out_h), background=(214, 208, 196))


def run_control_extract(skip_char: str = "Я") -> ExtractedSheet:
    """Контроль без руки: программа сама кладёт черту в клетки и сверяет подписи."""
    laid_out = build_propisi_images()
    first_layout, first_image = laid_out[0]
    painted = paint_control_ink(first_image, first_layout.cells, skip_char=skip_char)
    photo = skew_photo(painted)
    layouts = [layout for layout, _image in laid_out]
    return extract_sheet(photo, layouts)


def _dark_centroid(
    gray: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> tuple[float, float] | None:
    window = gray[y0:y1, x0:x1]
    mask = window < DARK_MARKER
    if int(mask.sum()) < 30:
        return None
    height, width = mask.shape
    corner_x = 0 if x0 == 0 else width - 1
    corner_y = 0 if y0 == 0 else height - 1
    ys, xs = np.nonzero(mask)
    distance = (xs - corner_x) ** 2 + (ys - corner_y) ** 2
    order = np.argsort(distance)
    seen = np.zeros(mask.shape, dtype=bool)
    for index in order[:400]:
        start_x = int(xs[index])
        start_y = int(ys[index])
        if seen[start_y, start_x]:
            continue
        count, mean_x, mean_y = _flood(mask, seen, start_x, start_y)
        if count >= 80:
            return (mean_x + x0, mean_y + y0)
    return None


def _flood(mask: np.ndarray, seen: np.ndarray, start_x: int, start_y: int) -> tuple[int, float, float]:
    height, width = mask.shape
    queue: deque[tuple[int, int]] = deque([(start_x, start_y)])
    seen[start_y, start_x] = True
    sum_x = 0
    sum_y = 0
    count = 0
    while queue:
        x_coord, y_coord = queue.popleft()
        sum_x += x_coord
        sum_y += y_coord
        count += 1
        for step_x, step_y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            next_x = x_coord + step_x
            next_y = y_coord + step_y
            if next_x < 0 or next_y < 0 or next_x >= width or next_y >= height:
                continue
            if seen[next_y, next_x] or not mask[next_y, next_x]:
                continue
            seen[next_y, next_x] = True
            queue.append((next_x, next_y))
    if count == 0:
        return 0, 0.0, 0.0
    return count, sum_x / count, sum_y / count


def _ensure_spread(centers: list[tuple[float, float]]) -> None:
    xs = [point[0] for point in centers]
    ys = [point[1] for point in centers]
    if max(xs) - min(xs) < 80 or max(ys) - min(ys) < 80:
        raise SheetError("Метки на фото стоят слишком близко. Сними лист целиком.")
