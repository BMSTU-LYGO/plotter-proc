import pytest

from plotter_processor.math_expression import (
    MathValidationStatus,
    normalize_latex_expression,
    require_renderable,
)


def test_normalized_model_distinguishes_core_math_nodes() -> None:
    model = normalize_latex_expression(
        r"\sum_{i=0}^{n} \frac{\sqrt{x_i}}{\sin(x)}"
    )

    kinds = {node.kind for node in model.root.children}
    assert model.status is MathValidationStatus.SUPPORTED
    assert {"n-ary", "subscript", "superscript", "fraction", "root", "function"} <= kinds


@pytest.mark.parametrize("command", ["input", "include", "newcommand", "def"])
def test_dangerous_latex_is_forbidden_before_rendering(command: str) -> None:
    model = normalize_latex_expression(rf"\{command}{{payload}}")

    assert model.status is MathValidationStatus.FORBIDDEN
    with pytest.raises(ValueError, match="Forbidden LaTeX command"):
        require_renderable(model)


def test_unsupported_and_invalid_latex_have_distinct_diagnostics() -> None:
    unsupported = normalize_latex_expression(r"\foo{x}")
    invalid = normalize_latex_expression(r"\frac{x}{y")

    assert unsupported.status is MathValidationStatus.PARTIALLY_SUPPORTED
    assert unsupported.diagnostics[0].message == r"Unsupported LaTeX command: \foo"
    assert invalid.status is MathValidationStatus.INVALID
    assert invalid.diagnostics[0].message == "Unclosed LaTeX delimiter: {"
