"""Графики только из белого списка. Текст как программа не выполняется."""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


class GraphError(Exception):
    pass


@dataclass(frozen=True)
class GraphSpec:
    kind: str
    x0: float
    x1: float
    k: float = 1.0
    b: float = 0.0


_LINE = re.compile(
    r"^график:y=(?P<expr>.+?)от(?P<a>[+-]?\d+(?:\.\d+)?)до(?P<b>[+-]?\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)

_EXACT = {
    "log2(x)": ("log2", 1.0, 0.0),
    "ln(x)": ("ln", 1.0, 0.0),
    "log10(x)": ("log10", 1.0, 0.0),
    "sqrt(x)": ("sqrt", 1.0, 0.0),
    "exp(x)": ("exp", 1.0, 0.0),
    "sin(x)": ("sin", 1.0, 0.0),
    "x": ("x", 1.0, 0.0),
    "x^2": ("x2", 1.0, 0.0),
}

_LINEAR = re.compile(r"^(?P<k>[+-]?(?:\d+(?:\.\d+)?)?)?\*?x(?P<b>[+-]\d+(?:\.\d+)?)?$")


def parse_graph_line(line: str) -> GraphSpec | None:
    compact = (
        line.strip()
        .lower()
        .replace(" ", "")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("**", "^")
    )
    if not compact.startswith("график:"):
        return None
    matched = _LINE.fullmatch(compact)
    if not matched:
        raise GraphError(
            "Этот график я не понял. Напиши, например: график: y = log2(x) от 0.1 до 8"
        )
    parsed = _parse_expr(matched.group("expr"))
    if parsed is None:
        raise GraphError(
            "Такую формулу для графика я не рисую. Можно log2, ln, log10, sqrt, exp, sin, x, x^2 и прямую k*x+b."
        )
    kind, k_value, b_value = parsed
    x0 = float(matched.group("a"))
    x1 = float(matched.group("b"))
    if x1 <= x0:
        raise GraphError("Конец графика должен быть правее начала")
    _check_domain(kind, x0, x1)
    return GraphSpec(kind, x0, x1, k_value, b_value)


def value_at(spec: GraphSpec, x_coord: float) -> float:
    return _apply(spec.kind, x_coord, spec.k, spec.b)


def sample_curve(spec: GraphSpec, count: int = 240) -> tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(spec.x0, spec.x1, count)
    ys = np.array([_apply(spec.kind, float(x_coord), spec.k, spec.b) for x_coord in xs], dtype=np.float64)
    return xs, ys


def render_graph(spec: GraphSpec) -> Image.Image:
    xs, ys = sample_curve(spec)
    finite = np.isfinite(ys)
    if not np.any(finite):
        raise GraphError("На этом промежутке график не считается")
    figure, axes = plt.subplots(figsize=(7.2, 3.8), dpi=110)
    axes.plot(xs[finite], ys[finite], color="#1a3c8f", linewidth=2.2)
    axes.set_xlabel("x")
    axes.set_ylabel("y")
    axes.grid(True, color="#d5dbe6")
    axes.set_facecolor("#f8fbff")
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def _parse_expr(expr: str) -> tuple[str, float, float] | None:
    if expr in _EXACT:
        kind, k_value, b_value = _EXACT[expr]
        return kind, k_value, b_value
    if "^" in expr or "(" in expr:
        return None
    matched = _LINEAR.fullmatch(expr)
    if not matched:
        return None
    raw_k = matched.group("k")
    if raw_k in (None, "", "+"):
        k_value = 1.0
    elif raw_k == "-":
        k_value = -1.0
    else:
        k_value = float(raw_k)
    raw_b = matched.group("b")
    b_value = float(raw_b) if raw_b else 0.0
    return "linear", k_value, b_value


def _check_domain(kind: str, x0: float, x1: float) -> None:
    if kind in {"log2", "ln", "log10"} and x0 <= 0:
        raise GraphError("Логарифм считается только при x больше нуля")
    if kind == "sqrt" and x0 < 0:
        raise GraphError("Корень считается только при x от нуля и правее")


def _apply(kind: str, x_coord: float, k_value: float, b_value: float) -> float:
    if kind == "log2":
        return math.log2(x_coord)
    if kind == "ln":
        return math.log(x_coord)
    if kind == "log10":
        return math.log10(x_coord)
    if kind == "sqrt":
        return math.sqrt(x_coord)
    if kind == "exp":
        try:
            return math.exp(x_coord)
        except OverflowError as exc:
            raise GraphError("Слишком большие числа для графика") from exc
    if kind == "sin":
        return math.sin(x_coord)
    if kind == "x":
        return x_coord
    if kind == "x2":
        return x_coord * x_coord
    if kind == "linear":
        return k_value * x_coord + b_value
    raise GraphError("неизвестный вид графика")
