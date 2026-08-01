from __future__ import annotations

import math
from pathlib import Path

import yaml

from plotter_processor.centerline_font.models import CenterlineGlyph, CenterlineStroke
from plotter_processor.models import Point


def load_glyph_patch(path: Path, expected_font_sha256: str) -> dict[str, CenterlineGlyph | dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("Unsupported or invalid centerline patch version")
    digest = raw.get("font_sha256")
    if digest != expected_font_sha256:
        raise ValueError("Centerline patch font SHA-256 does not match the selected font")
    glyphs = raw.get("glyphs")
    if not isinstance(glyphs, dict):
        raise TypeError("Centerline patch glyphs must be a mapping")
    return glyphs


def apply_glyph_patch(glyph: CenterlineGlyph, raw: object) -> CenterlineGlyph:
    if not isinstance(raw, dict) or raw.get("mode") != "replace":
        raise ValueError("Centerline patch v1 supports only mode: replace")
    advance = raw.get("advance_font_units", glyph.advance_font_units)
    if isinstance(advance, bool) or not isinstance(advance, (int, float)) or advance <= 0:
        raise ValueError("Centerline patch advance_font_units must be positive")
    raw_strokes = raw.get("strokes")
    if not isinstance(raw_strokes, list) or not raw_strokes:
        raise ValueError("Centerline patch requires at least one stroke")
    strokes: list[CenterlineStroke] = []
    for stroke_id, item in enumerate(raw_strokes):
        if not isinstance(item, dict) or set(item) - {"closed", "points"}:
            raise ValueError("Invalid centerline patch stroke")
        closed = item.get("closed", False)
        points = item.get("points")
        if not isinstance(closed, bool) or not isinstance(points, list):
            raise TypeError("Invalid centerline patch stroke fields")
        minimum = 3 if closed else 2
        if len(points) < minimum:
            raise ValueError("Centerline patch stroke has too few points")
        converted: list[Point] = []
        for point in points:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in point)
                or any(not math.isfinite(float(value)) for value in point)
            ):
                raise ValueError("Centerline patch point must contain two finite numbers")
            converted.append(Point(float(point[0]), float(point[1])))
        strokes.append(CenterlineStroke(stroke_id, tuple(converted), closed, stroke_id))
    quality = dict(glyph.quality)
    quality.update({"source": "manual_patch", "needs_review": False, "quality_status": "patched"})
    return CenterlineGlyph(
        glyph.char,
        glyph.codepoint,
        glyph.glyph_name,
        int(advance),
        tuple(strokes),
        glyph.warnings,
        quality,
    )
