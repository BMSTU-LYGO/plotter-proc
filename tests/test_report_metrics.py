from pathlib import Path

import pytest

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CenterlineStroke,
    CompiledCenterlineFont,
)
from plotter_processor.models import PlotterStroke, Point, PositionedGlyph
from plotter_processor.pipeline import _centerline_report, _semantic_report


def test_centerline_report_uses_measured_retrace_and_populates_worst_glyphs() -> None:
    glyph = CenterlineGlyph(
        "A",
        ord("A"),
        "A",
        600,
        (
            CenterlineStroke(
                0,
                (Point(0, 0), Point(100, 0)),
                False,
                retraced_length_font_units=100,
            ),
        ),
        ("One-stroke retrace ratio exceeds configured limit",),
        {
            "mask_coverage": 0.91,
            "centerline_inside_mask_ratio": 0.99,
            "centerline_components": 1,
            "strokes_before_routing": 3,
            "strokes_after_routing": 1,
            "graph_edges": 3,
            "retrace_ratio": 0.25,
            "skeleton_method": "medial_axis",
            "quality_status": "needs_review",
            "needs_review": True,
        },
    )
    compiled = CompiledCenterlineFont(
        Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {"A": glyph}
    )
    positioned = PositionedGlyph("A", ord("A"), "A", 0, 10, 3, 0.005, 0, 0)

    report = _centerline_report(compiled, None, [positioned])

    assert report["retraced_length_mm"] == pytest.approx(0.5)
    assert report["retraced_length_measured"] is True
    assert report["worst_glyphs"] == [
        {
            "glyph": "A",
            "codepoint": "U+0041",
            "coverage": 0.91,
            "inside_mask": 0.99,
            "components": 1,
            "routes_before": 3,
            "routes_after": 1,
            "retrace_ratio": 0.25,
            "method": "medial_axis",
            "quality_status": "needs_review",
            "warning": "One-stroke retrace ratio exceeds configured limit",
        }
    ]


def test_semantic_report_measures_conflicts_without_claiming_suppression() -> None:
    strokes = [
        PlotterStroke(
            0,
            [Point(1, 2), Point(3, 4)],
            False,
            semantic_role="underline",
        ),
        PlotterStroke(
            1,
            [Point(1, 2), Point(3, 4)],
            False,
            semantic_role="table-border",
        ),
    ]

    report = _semantic_report(strokes)

    assert report["classification_conflicts"] == 1
    assert report["classification_conflicts_measured"] is True
    assert report["duplicate_primitives_suppressed"] is None
