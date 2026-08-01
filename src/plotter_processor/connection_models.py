from __future__ import annotations

from dataclasses import dataclass

from plotter_processor.models import Point


@dataclass(frozen=True, slots=True)
class StrokeAnchor:
    point: Point
    tangent: Point
    side: str
    role: str
    confidence: float
    stroke_id: int
    point_index: int
    baseline_offset: float


@dataclass(frozen=True, slots=True)
class GlyphConnectionCandidate:
    left_glyph_index: int
    right_glyph_index: int
    left_exit: StrokeAnchor
    right_entry: StrokeAnchor
    distance_mm: float
    tangent_mismatch_deg: float
    vertical_offset_mm: float
    corridor_inside_ratio: float
    collision_count: int
    score: float
    accepted: bool
    rejection_reason: str | None = None
