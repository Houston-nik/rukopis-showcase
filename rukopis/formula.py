"""Формулы из своих знаков: степень, индекс, дробь и корень. Чужой буквой дырку не закрываем."""

from __future__ import annotations

from dataclasses import dataclass
from PIL import Image

MISSING_COLOR = (255, 214, 80, 255)


@dataclass
class CharNode:
    char: str


@dataclass
class ScriptNode:
    base: object
    sup: list[object] | None
    sub: list[object] | None


@dataclass
class FracNode:
    numerator: list[object]
    denominator: list[object]


@dataclass
class SqrtNode:
    inner: list[object]


Node = CharNode | ScriptNode | FracNode | SqrtNode


def parse_formula(text: str) -> list[Node]:
    nodes, _index = _parse_until(text, 0, None)
    return nodes


def render_formula(text: str, glyphs: dict[str, Image.Image], glyph_h: int = 40) -> tuple[Image.Image, list[str]]:
    nodes = parse_formula(text)
    missing: list[str] = []
    image = _render_nodes(nodes, glyphs, glyph_h, missing)
    return image, _unique(missing)


def _parse_until(text: str, index: int, stop: str | None) -> tuple[list[Node], int]:
    nodes: list[Node] = []
    length = len(text)
    while index < length:
        start_index = index
        if stop is not None and text[index] == stop:
            break
        if text.startswith("\\frac{", index):
            numerator, index = _read_group(text, index + 5)
            if index >= length or text[index] != "{":
                nodes.append(CharNode("\\"))
                continue
            denominator, index = _read_group(text, index)
            nodes.append(FracNode(numerator, denominator))
            continue
        if text.startswith("\\sqrt{", index):
            inner, index = _read_group(text, index + 5)
            nodes.append(SqrtNode(inner))
            continue
        char = text[index]
        if char in {"^", "_"} and nodes:
            body, index = _read_script(text, index + 1)
            target = nodes[-1]
            if isinstance(target, ScriptNode):
                if char == "^" and target.sup is None:
                    target.sup = body
                elif char == "_" and target.sub is None:
                    target.sub = body
                else:
                    nodes.append(ScriptNode(CharNode(char), body if char == "^" else None, body if char == "_" else None))
            else:
                nodes[-1] = ScriptNode(
                    target,
                    body if char == "^" else None,
                    body if char == "_" else None,
                )
            continue
        if char == " ":
            index += 1
            nodes.append(CharNode(" "))
            continue
        nodes.append(CharNode(char))
        index += 1
        if index == start_index:
            index += 1
    return nodes, index


def _read_group(text: str, index: int) -> tuple[list[Node], int]:
    if index >= len(text) or text[index] != "{":
        return [], index
    inner, index = _parse_until(text, index + 1, "}")
    if index < len(text) and text[index] == "}":
        index += 1
    return inner, index


def _read_script(text: str, index: int) -> tuple[list[Node], int]:
    if index < len(text) and text[index] == "{":
        return _read_group(text, index)
    if index >= len(text):
        return [], index
    return [CharNode(text[index])], index + 1


def _render_nodes(
    nodes: list[Node],
    glyphs: dict[str, Image.Image],
    glyph_h: int,
    missing: list[str],
) -> Image.Image:
    if glyph_h < 8:
        glyph_h = 8
    placed: list[tuple[Image.Image, int, int]] = []
    x_cursor = 0
    line_top = 0
    line_bottom = glyph_h
    for node in nodes:
        sprite, top = _sprite_for(node, glyphs, glyph_h, missing)
        placed.append((sprite, x_cursor, top))
        line_top = min(line_top, top)
        line_bottom = max(line_bottom, top + sprite.height)
        x_cursor += sprite.width + 1
    width = max(1, x_cursor)
    height = max(1, line_bottom - line_top)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for sprite, x_pos, top in placed:
        canvas.paste(sprite, (x_pos, top - line_top), sprite)
    return canvas


def _sprite_for(
    node: Node,
    glyphs: dict[str, Image.Image],
    glyph_h: int,
    missing: list[str],
) -> tuple[Image.Image, int]:
    if isinstance(node, CharNode):
        image = _char_image(node.char, glyphs, glyph_h, missing)
        return image, 0
    if isinstance(node, ScriptNode):
        base, _base_top = _sprite_for(node.base, glyphs, glyph_h, missing)  # type: ignore[arg-type]
        small_h = max(8, int(glyph_h * 0.55))
        sup_image = _render_nodes(node.sup or [], glyphs, small_h, missing) if node.sup else None
        sub_image = _render_nodes(node.sub or [], glyphs, small_h, missing) if node.sub else None
        sup_w = sup_image.width if sup_image else 0
        sub_w = sub_image.width if sub_image else 0
        width = base.width + max(sup_w, sub_w)
        sup_top = -int(glyph_h * 0.42)
        base_top = 0
        sub_top = int(glyph_h * 0.62)
        top = sup_top if sup_image else 0
        bottom = base.height
        if sub_image:
            bottom = max(bottom, sub_top + sub_image.height)
        height = bottom - top
        canvas = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
        canvas.paste(base, (0, base_top - top), base)
        if sup_image is not None:
            canvas.paste(sup_image, (base.width, sup_top - top), sup_image)
        if sub_image is not None:
            canvas.paste(sub_image, (base.width, sub_top - top), sub_image)
        return canvas, top
    if isinstance(node, FracNode):
        small_h = max(8, int(glyph_h * 0.7))
        numerator = _render_nodes(node.numerator, glyphs, small_h, missing)
        denominator = _render_nodes(node.denominator, glyphs, small_h, missing)
        width = max(numerator.width, denominator.width, 8) + 6
        height = numerator.height + denominator.height + 8
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(numerator, ((width - numerator.width) // 2, 0), numerator)
        bar_y = numerator.height + 3
        for x_pos in range(2, width - 2):
            canvas.putpixel((x_pos, bar_y), (25, 45, 130, 255))
        canvas.paste(denominator, ((width - denominator.width) // 2, bar_y + 4), denominator)
        return canvas, 0
    if isinstance(node, SqrtNode):
        inner = _render_nodes(node.inner, glyphs, glyph_h, missing)
        radical = _char_image("√", glyphs, inner.height + 6, missing)
        width = radical.width + inner.width + 2
        height = max(radical.height, inner.height + 4)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(radical, (0, height - radical.height), radical)
        canvas.paste(inner, (radical.width, 4), inner)
        return canvas, 0
    raise TypeError(f"неизвестный кусок формулы: {type(node)!r}")


def _char_image(
    char: str,
    glyphs: dict[str, Image.Image],
    glyph_h: int,
    missing: list[str],
) -> Image.Image:
    if char == " ":
        return Image.new("RGBA", (max(8, glyph_h // 3), glyph_h), (0, 0, 0, 0))
    glyph = glyphs.get(char)
    if glyph is None and char in {"-", "–", "—"}:
        glyph = glyphs.get("−")
    if glyph is None:
        missing.append(char)
        return _missing_box(glyph_h)
    return _scale(glyph, glyph_h)


def _scale(glyph: Image.Image, glyph_h: int) -> Image.Image:
    width, height = glyph.size
    if height <= 0:
        return glyph
    new_h = max(1, glyph_h)
    new_w = max(1, int(width * new_h / height))
    return glyph.resize((new_w, new_h), Image.Resampling.NEAREST)


def _missing_box(glyph_h: int) -> Image.Image:
    width = max(14, int(glyph_h * 0.7))
    image = Image.new("RGBA", (width, glyph_h), (0, 0, 0, 0))
    box = Image.new("RGBA", (width - 2, glyph_h - 2), MISSING_COLOR)
    image.paste(box, (1, 1))
    return image


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen and item != " ":
            seen.append(item)
    return seen
