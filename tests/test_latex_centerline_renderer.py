import math

import pytest

from plotter_processor.latex_renderer import MathTextRenderer


@pytest.mark.parametrize(
    "expression",
    [
        r"x^2+x_i",
        r"\frac{a+b}{c-d}",
        r"\sqrt{x^2+1}",
        r"\sum_{i=1}^{n}i",
        r"\int_0^1f(x)\,dx",
        r"\alpha+\beta\leq\pi",
    ],
)
def test_default_mathtext_is_single_centerline_geometry(expression: str) -> None:
    rendered = MathTextRenderer().render(expression, 5.0)

    assert rendered.stroke_mode == "centerline"
    assert rendered.quality["mask_foreground_pixels"] > 0
    assert rendered.quality["centerline_coverage_ratio"] > 0
    assert all(stroke.segment_types == ("latex-centerline",) for stroke in rendered.strokes)
    assert all(
        math.isfinite(point.x) and math.isfinite(point.y)
        for stroke in rendered.strokes
        for point in stroke.points
    )


def test_explicit_outline_mode_remains_compatible() -> None:
    rendered = MathTextRenderer(stroke_mode="outline").render("x^2", 5.0)

    assert rendered.stroke_mode == "outline"
    assert all(stroke.segment_types == ("latex-outline",) for stroke in rendered.strokes)
