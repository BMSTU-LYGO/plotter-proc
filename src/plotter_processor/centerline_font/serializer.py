from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CenterlineStroke,
    CompiledCenterlineFont,
    CompiledGlyphAnchor,
    CompiledStrokeMetadata,
)
from plotter_processor.models import Point
from plotter_processor.performance import glyph_performance, measure_glyph_stage
from plotter_processor.schemas import COMPILED_FONT_SCHEMA_VERSION

FORMAT = "plotter-centerline-font"
VERSION = COMPILED_FONT_SCHEMA_VERSION


def to_data(font: CompiledCenterlineFont, *, config: dict[str, object]) -> dict[str, object]:
    return {
        "format": FORMAT,
        "version": VERSION,
        "font_sha256": font.font_sha256,
        "source_fingerprint": font.source_fingerprint,
        "font_path": str(font.font_path),
        "config": config,
        "metrics": {
            "units_per_em": font.units_per_em,
            "ascent": font.ascent,
            "descent": font.descent,
            "line_gap": font.line_gap,
        },
        "glyphs": {
            char: _glyph_to_data(char, glyph)
            for char, glyph in sorted(font.glyphs.items(), key=lambda item: ord(item[0]))
        },
        "warnings": font.warnings,
    }


def _glyph_to_data(char: str, glyph: CenterlineGlyph) -> dict[str, object]:
    with glyph_performance(char), measure_glyph_stage("serialization"):
        return {
            "codepoint": glyph.codepoint,
            "glyph_name": glyph.glyph_name,
            "advance_font_units": glyph.advance_font_units,
            "strokes": [
                {
                    "id": stroke.id,
                    "component_id": stroke.component_id,
                    "closed": stroke.closed,
                    "retraced_length_font_units": stroke.retraced_length_font_units,
                    "points": [[point.x, point.y] for point in stroke.points],
                }
                for stroke in glyph.strokes
            ],
            "warnings": list(glyph.warnings),
            "quality": glyph.quality,
            "entry_anchor": _anchor_to_data(glyph.entry_anchor),
            "exit_anchor": _anchor_to_data(glyph.exit_anchor),
            "stroke_metadata": [
                {
                    "stroke_id": metadata.stroke_id,
                    "component_id": metadata.component_id,
                    "closed": metadata.closed,
                    "retraced_length_font_units": metadata.retraced_length_font_units,
                    "recommended_order": metadata.recommended_order,
                    "recommended_direction": metadata.recommended_direction,
                }
                for metadata in glyph.stroke_metadata
            ],
        }


def _anchor_to_data(anchor: CompiledGlyphAnchor | None) -> dict[str, object] | None:
    if anchor is None:
        return None
    return {
        "point": [anchor.point.x, anchor.point.y],
        "stroke_id": anchor.stroke_id,
        "point_index": anchor.point_index,
    }


def from_data(data: object, path: str | Path = "<memory>") -> CompiledCenterlineFont:
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != VERSION:
        raise ValueError("Unsupported centerline font cache")
    metrics = _dict(data.get("metrics"), "metrics")
    glyphs_data = _dict(data.get("glyphs"), "glyphs")
    glyphs: dict[str, CenterlineGlyph] = {}
    for char, raw in glyphs_data.items():
        if not isinstance(char, str) or len(char) != 1:
            raise ValueError("Invalid centerline glyph key")
        item = _dict(raw, f"glyph {char}")
        strokes: list[CenterlineStroke] = []
        raw_strokes = item.get("strokes")
        if not isinstance(raw_strokes, list):
            raise TypeError(f"Invalid strokes for {char}")
        for raw_stroke in raw_strokes:
            stroke = _dict(raw_stroke, "stroke")
            raw_points = stroke.get("points")
            if not isinstance(raw_points, list):
                raise TypeError("Invalid stroke points")
            points = tuple(Point(float(p[0]), float(p[1])) for p in raw_points)
            if any(not math.isfinite(p.x) or not math.isfinite(p.y) for p in points):
                raise ValueError("Non-finite centerline coordinate")
            closed = bool(stroke.get("closed"))
            if len(set(points)) < (3 if closed else 2):
                raise ValueError("Centerline stroke has too few unique points")
            strokes.append(
                CenterlineStroke(
                    int(stroke.get("id", len(strokes))),
                    points,
                    closed,
                    int(stroke.get("component_id", 0)),
                    float(stroke.get("retraced_length_font_units", 0.0)),
                )
            )
        raw_metadata = item.get("stroke_metadata", [])
        if not isinstance(raw_metadata, list):
            raise TypeError(f"Invalid stroke metadata for {char}")
        glyphs[char] = CenterlineGlyph(
            char,
            int(item["codepoint"]),
            str(item["glyph_name"]),
            int(item["advance_font_units"]),
            tuple(strokes),
            tuple(str(w) for w in item.get("warnings", [])),
            dict(_dict(item.get("quality", {}), "quality")),
            _anchor_from_data(item.get("entry_anchor")),
            _anchor_from_data(item.get("exit_anchor")),
            tuple(
                CompiledStrokeMetadata(
                    int(_dict(raw, "stroke metadata")["stroke_id"]),
                    int(_dict(raw, "stroke metadata")["component_id"]),
                    bool(_dict(raw, "stroke metadata")["closed"]),
                    float(
                        _dict(raw, "stroke metadata").get(
                            "retraced_length_font_units", 0.0
                        )
                    ),
                    (
                        int(_dict(raw, "stroke metadata")["recommended_order"])
                        if _dict(raw, "stroke metadata").get("recommended_order")
                        is not None
                        else None
                    ),
                    str(
                        _dict(raw, "stroke metadata").get(
                            "recommended_direction", "auto"
                        )
                    ),
                )
                for raw in raw_metadata
            ),
        )
    return CompiledCenterlineFont(
        Path(str(data.get("font_path", path))),
        str(data["font_sha256"]),
        int(metrics["units_per_em"]),
        int(metrics["ascent"]),
        int(metrics["descent"]),
        int(metrics["line_gap"]),
        glyphs,
        [str(w) for w in data.get("warnings", [])],
    )


def _anchor_from_data(value: object) -> CompiledGlyphAnchor | None:
    if value is None:
        return None
    anchor = _dict(value, "glyph anchor")
    point = anchor.get("point")
    if not isinstance(point, list) or len(point) != 2:
        raise TypeError("Invalid glyph anchor point")
    return CompiledGlyphAnchor(
        Point(float(point[0]), float(point[1])),
        int(anchor["stroke_id"]),
        int(anchor["point_index"]),
    )


def load_centerline_font(path: str | Path) -> tuple[CompiledCenterlineFont, dict[str, object]]:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read centerline cache: {source}") from error
    font = from_data(data, source)
    return font, dict(_dict(data.get("config"), "config"))


def write_centerline_font_atomic(
    font: CompiledCenterlineFont, path: str | Path, *, config: dict[str, object]
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_data(font, config=config), ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _dict(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"Invalid centerline cache field: {name}")
    return value
