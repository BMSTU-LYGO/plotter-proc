import inspect
import math
from pathlib import Path

import pytest

import plotter_processor.latex_renderer as renderer_module
from plotter_processor.latex_renderer import MathTextRenderer, export_latex_debug


@pytest.mark.parametrize(
    "expression",
    [r"x^2", r"x_1+x_2", r"\frac{a}{b}", r"\sqrt{x}", r"\alpha+\beta", r"\sum_0^n+\int_0^1x dx"],
)
def test_mathtext_renders_finite_vector_strokes(expression: str) -> None:
    rendered = MathTextRenderer().render(expression, 5.0)

    assert rendered.strokes
    assert rendered.width_mm > 0
    assert rendered.height_mm > 0
    assert 0 <= rendered.baseline_mm <= rendered.height_mm + 5
    assert all(
        math.isfinite(point.x) and math.isfinite(point.y)
        for stroke in rendered.strokes
        for point in stroke.points
    )
    assert all(stroke.element_type == "latex" for stroke in rendered.strokes)


def test_debug_artifacts_and_no_shell_backend(tmp_path: Path) -> None:
    rendered = MathTextRenderer().render(r"\frac{1}{3}", 5.0)
    export_latex_debug(
        rendered,
        tmp_path / "formula.svg",
        tmp_path / "formula.json",
        formula_index=1,
        display_mode=True,
        source_syntax="dollar-block",
    )

    assert (tmp_path / "formula.svg").is_file()
    assert (tmp_path / "formula.json").is_file()
    source = inspect.getsource(renderer_module)
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "shell=True" not in source


def test_unsupported_command_has_clear_error() -> None:
    with pytest.raises(ValueError, match="MathText cannot render"):
        MathTextRenderer().render(r"\definitelyunsupported{x}", 5.0)
