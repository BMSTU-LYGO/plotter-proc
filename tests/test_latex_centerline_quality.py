import math

import pytest

from plotter_processor.latex_renderer import MathTextRenderer, _evaluate_math_geometry
from plotter_processor.models import PlotterStroke, Point


def test_formula_quality_contains_bounded_topology_metrics() -> None:
    rendered = MathTextRenderer(strict_quality=True).render(r"\frac{a}{b}", 5.0)

    expected = {
        "components_before_pruning",
        "components_after_pruning",
        "graph_nodes",
        "graph_edges",
        "junction_count",
        "strokes",
        "points",
        "draw_length_mm",
        "retraced_length_mm",
        "retrace_ratio",
        "centerline_coverage_ratio",
        "needs_review",
    }
    assert expected <= rendered.quality.keys()
    assert rendered.quality["points"] <= 150_000
    assert rendered.quality["quality_failures"] == ()


def test_quality_gate_detects_corrupt_structure_and_non_finite_geometry() -> None:
    strokes = [
        PlotterStroke(0, [Point(0.0, 0.0), Point(math.nan, 1.0)], False),
        PlotterStroke(1, [Point(0.0, 0.0), Point(1.0, 0.0)], False),
        PlotterStroke(2, [Point(1.0, 0.0), Point(0.0, 0.0)], False),
    ]

    quality = _evaluate_math_geometry(
        strokes,
        1.0,
        1.0,
        expected_glyphs=2,
        lost_glyphs=1,
        expected_structural_lines=1,
        structural_lines=0,
        max_components=2,
        max_points=100,
    )

    assert {
        "non_finite_geometry",
        "too_many_components",
        "lost_glyphs",
        "lost_structural_lines",
    } <= set(quality["quality_failures"])


def test_quality_gate_detects_bbox_retrace_and_pen_lifts() -> None:
    repeated = [Point(0.0, 0.0), Point(8.0, 0.0)]
    strokes = [PlotterStroke(index, list(repeated), False) for index in range(20)]

    quality = _evaluate_math_geometry(
        strokes,
        2.0,
        2.0,
        expected_glyphs=1,
        lost_glyphs=0,
        expected_structural_lines=0,
        structural_lines=0,
        max_components=100,
        max_points=100,
    )

    assert {
        "geometry_outside_formula_bbox",
        "unexpected_formula_bbox",
        "excessive_retrace",
        "too_many_pen_lifts",
    } <= set(quality["quality_failures"])


def test_strict_quality_does_not_hide_double_renderer_failure_in_outline() -> None:
    renderer = MathTextRenderer(
        max_components=1,
        fallback_to_outline=True,
        strict_quality=True,
    )

    with pytest.raises(ValueError, match="components|quality gate"):
        renderer.render("x+y+z", 5.246)


@pytest.mark.parametrize(
    ("expression", "minimum_points"),
    [(r"\alpha", 20), (r"\beta", 20), (r"\infty", 16), ("0", 14), ("8", 20)],
)
def test_counter_glyphs_keep_their_inner_geometry(
    expression: str, minimum_points: int
) -> None:
    rendered = MathTextRenderer(strict_quality=True).render(expression, 5.0)
    points = sum(len(stroke.points) for stroke in rendered.strokes)
    left, top, right, bottom = rendered.quality["formula_bbox"]

    assert points >= minimum_points
    assert bottom - top >= (right - left) * 0.45
