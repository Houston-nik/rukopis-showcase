"""Точки проверки: прописи, азбука, формулы, график, PDF, журнал и безопасность."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rukopis.extract import glyph_from_cell, run_control_extract
from rukopis.formula import render_formula
from rukopis.graph import GraphError, parse_graph_line, render_graph, value_at
from rukopis.layout import REQUIRED_ON_SHEET, build_pages, chars_on_sheets, marker_boxes
from rukopis.logutil import log_step
from rukopis.pdf_export import save_pdf
from rukopis.propisi import build_propisi_images
from rukopis.render import render_document
from rukopis.security import HOST, SecurityError, assert_local_bind, check_upload, safe_child
from rukopis.textin import lightly_compress


def _blob(color: tuple[int, int, int], width: int = 18, height: int = 36) -> Image.Image:
    return Image.new("RGBA", (width, height), color + (255,))


def _atlas() -> dict[str, Image.Image]:
    glyphs = {char: _blob((20, 40, 110)) for char in chars_on_sheets()}
    glyphs["x"] = _blob((220, 20, 20))
    glyphs["2"] = _blob((20, 20, 220))
    glyphs["a"] = _blob((220, 20, 20))
    glyphs["1"] = _blob((20, 180, 20))
    return glyphs


class Checkpoints(unittest.TestCase):
    def test_propisi_has_letters_digits_signs_and_markers(self) -> None:
        pages = build_propisi_images()
        self.assertGreaterEqual(len(pages), 3)
        self.assertLessEqual(len(pages), 4)
        self.assertTrue(REQUIRED_ON_SHEET <= chars_on_sheets())
        image = pages[0][1]
        for x_coord, y_coord, width, height in marker_boxes():
            pixel = image.getpixel((x_coord + width // 2, y_coord + height // 2))
            self.assertLess(pixel[0], 10)

    def test_control_extract_matches_labels_and_skips_empty(self) -> None:
        sheet = run_control_extract(skip_char="Я")
        cells = build_pages()[0].cells
        self.assertEqual(sheet.page_index, 0)
        self.assertIn("Я", sheet.empty)
        self.assertNotIn("Я", sheet.glyphs)
        for cell in cells:
            if cell.char == "Я":
                continue
            self.assertIn(cell.char, sheet.glyphs)

    def test_gray_hint_is_not_ink(self) -> None:
        layout, image = build_propisi_images()[0]
        self.assertIsNone(glyph_from_cell(image, layout.cells[0]))

    def test_line_wraps_inside_page(self) -> None:
        result = render_document("мама " * 80, _atlas())
        self.assertGreaterEqual(result.line_count, 2)
        self.assertTrue(result.line_widths)
        self.assertTrue(all(width <= result.content_width + 2 for width in result.line_widths))

    def test_missing_sign_is_yellow_and_not_replaced(self) -> None:
        glyphs = {char: _blob((20, 40, 110)) for char in chars_on_sheets() if char != "Б"}
        result = render_document("Б", glyphs)
        self.assertIn("Б", result.missing)
        pixels = np.asarray(result.pages[0].convert("RGB"))
        yellow = (pixels[:, :, 0] > 230) & (pixels[:, :, 1] > 180) & (pixels[:, :, 2] < 140)
        self.assertTrue(yellow.any())

    def test_power_sits_above_and_index_below(self) -> None:
        glyphs = _atlas()
        power, power_missing = render_formula("x^2", glyphs, 40)
        self.assertEqual(power_missing, [])
        power_px = np.asarray(power)
        red = (power_px[:, :, 0] > 180) & (power_px[:, :, 2] < 90) & (power_px[:, :, 3] > 200)
        blue = (power_px[:, :, 2] > 180) & (power_px[:, :, 0] < 90) & (power_px[:, :, 3] > 200)
        self.assertTrue(red.any())
        self.assertTrue(blue.any())
        self.assertLess(np.nonzero(blue)[0].mean(), np.nonzero(red)[0].mean())

        index, index_missing = render_formula("a_1", glyphs, 40)
        self.assertEqual(index_missing, [])
        index_px = np.asarray(index)
        base = (index_px[:, :, 0] > 180) & (index_px[:, :, 1] < 80) & (index_px[:, :, 3] > 200)
        sub = (index_px[:, :, 1] > 150) & (index_px[:, :, 0] < 80) & (index_px[:, :, 3] > 200)
        self.assertTrue(base.any())
        self.assertTrue(sub.any())
        self.assertGreater(np.nonzero(sub)[0].mean(), np.nonzero(base)[0].mean())

    def test_log2_points_and_drawn_curve(self) -> None:
        spec = parse_graph_line("график: y = log2(x) от 0.1 до 8")
        self.assertIsNotNone(spec)
        assert spec is not None
        expected = {1: 0.0, 2: 1.0, 4: 2.0, 8: 3.0}
        for x_coord, want in expected.items():
            self.assertAlmostEqual(value_at(spec, x_coord), want)
        image = render_graph(spec)
        self.assertGreater(image.size[0], 80)
        self.assertGreater(np.asarray(image).std(), 5)
        with self.assertRaises(GraphError):
            parse_graph_line("график: y = __import__('os') от 0 до 1")

    def test_pdf_page_count_matches_images(self) -> None:
        result = render_document("Первая строка\nграфик: y = x^2 от -2 до 2\nВторая строка", _atlas())
        self.assertGreaterEqual(len(result.pages), 1)
        self.assertEqual(result.graph_count, 1)
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "conspect.pdf"
            save_pdf(result.pages, dest)
            reader = PdfReader(str(dest))
            self.assertEqual(len(reader.pages), len(result.pages))

    def test_log_skips_conspect_text(self) -> None:
        secret = "СЕКРЕТНЫЙ ТЕКСТ КОНСПЕКТА 12345"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rukopis.log"
            log_step("render", log_path=path, glyphs=3, missing=1, conspect=secret, text=secret)
            written = path.read_text(encoding="utf-8")
        self.assertNotIn(secret, written)
        record = json.loads(written)
        self.assertEqual(record["step"], "render")
        self.assertEqual(record["glyphs"], 3)
        self.assertNotIn("conspect", record)
        self.assertNotIn("text", record)

    def test_uploads_and_paths_are_limited(self) -> None:
        with self.assertRaises(SecurityError):
            check_upload("virus.exe", b"abc", "text")
        with self.assertRaises(SecurityError):
            check_upload("big.pdf", b"x" * (15 * 1024 * 1024 + 1), "text")
        self.assertEqual(check_upload("note.txt", "привет".encode("utf-8"), "text"), ".txt")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(SecurityError):
                safe_child(root, "..\\secret.txt")
            inside = safe_child(root, "page-1.png")
            self.assertEqual(inside.parent.resolve(), root.resolve())
        with self.assertRaises(SecurityError):
            assert_local_bind("0.0.0.0")
        self.assertEqual(assert_local_bind(HOST), "127.0.0.1")

    def test_short_mode_keeps_heading_and_graph(self) -> None:
        raw = "\n".join(
            [
                "# Логарифм",
                "А" * 400,
                "график: y = log2(x) от 0.1 до 8",
                "Короткое определение.",
            ]
        )
        short = lightly_compress(raw)
        self.assertIn("# Логарифм", short)
        self.assertIn("график: y = log2(x) от 0.1 до 8", short)
        self.assertIn("Короткое определение.", short)
        self.assertNotIn("А" * 400, short)

    def test_samples_folder_is_ignored_by_git(self) -> None:
        completed = subprocess.run(
            ["git", "check-ignore", "-v", "samples/secret-hand.png", "output/conspect.pdf", "atlas/glyphs/0410.png", "logs/rukopis.log"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        ignored = completed.stdout
        self.assertIn("samples/secret-hand.png", ignored)
        self.assertIn("output/conspect.pdf", ignored)
        self.assertIn("atlas/glyphs/0410.png", ignored)
        self.assertIn("logs/rukopis.log", ignored)


if __name__ == "__main__":
    unittest.main()
