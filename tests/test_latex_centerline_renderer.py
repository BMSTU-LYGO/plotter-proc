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
    assert rendered.quality["render_path"] == "vector-first"
    assert rendered.quality["glyphs_expected"] > 0
    assert rendered.quality["glyphs_lost"] == 0
    assert rendered.quality["centerline_coverage_ratio"] > 0
    assert all(
        stroke.segment_types in {("latex-centerline",), ("latex-structural-line",)}
        for stroke in rendered.strokes
    )
    assert all(
        math.isfinite(point.x) and math.isfinite(point.y)
        for stroke in rendered.strokes
        for point in stroke.points
    )


def test_explicit_outline_mode_remains_compatible() -> None:
    rendered = MathTextRenderer(stroke_mode="outline").render("x^2", 5.0)

    assert rendered.stroke_mode == "outline"
    assert all(stroke.segment_types == ("latex-outline",) for stroke in rendered.strokes)


@pytest.mark.parametrize(
    "expression",
    [r"\frac{x+1}{x-1}", r"\overline{x}", r"\underline{x}", r"\sqrt{x+1}"],
)
def test_math_lines_come_from_structural_geometry(expression: str) -> None:
    rendered = MathTextRenderer().render(expression, 5.0)

    structural = [
        stroke for stroke in rendered.strokes
        if stroke.segment_types == ("latex-structural-line",)
    ]
    assert len(structural) == 1
    assert len(structural[0].points) == 2
    assert structural[0].points[0].y == pytest.approx(structural[0].points[1].y)


def test_vector_failure_uses_whole_formula_raster_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = MathTextRenderer()
    monkeypatch.setattr(
        renderer,
        "_render_vector_centerline",
        lambda *_: (_ for _ in ()).throw(ValueError("forced vector failure")),
    )

    rendered = renderer.render("fallback_vector_case", 5.037)

    assert "latex_vector_raster_fallback" in rendered.warnings
    assert renderer.raster_fallbacks == 1


@pytest.mark.parametrize(
    "expression",
    [
        r"\sum_{i=0}^{n}",
        r"\prod_{k=1}^{m}",
        r"\int_0^\infty",
        r"\iint_A f(x)\,dx",
        r"\iiint_V f(x)\,dx",
        r"\lim_{x\to0}\frac{\sin x}{x}",
        r"x_{i_j}^{n^2}",
    ],
)
def test_large_operators_limits_and_nested_scripts_are_vector_first(expression: str) -> None:
    rendered = MathTextRenderer().render(expression, 5.0)

    assert rendered.quality["render_path"] == "vector-first"
    assert rendered.quality["glyphs_lost"] == 0
    assert not rendered.warnings


def test_left_right_delimiters_scale_with_nested_content() -> None:
    renderer = MathTextRenderer()
    simple = renderer.render(r"\left(x\right)", 5.0)
    nested = renderer.render(
        r"\left(\frac{x^2+1}{\sqrt{1-x}}\right)",
        5.0,
    )

    assert nested.height_mm > simple.height_mm * 1.5
    assert nested.quality["render_path"] == "vector-first"
