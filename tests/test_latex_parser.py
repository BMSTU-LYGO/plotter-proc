import pytest

from plotter_processor.latex_parser import MathRun, TextRun, parse_latex_runs


@pytest.mark.parametrize(
    ("source", "expression", "display"),
    [
        ("$x^2$", "x^2", False),
        (r"\(x_1 + x_2\)", "x_1 + x_2", False),
        (r"$$\frac{a}{b}$$", r"\frac{a}{b}", True),
        (r"\[\sqrt{x}\]", r"\sqrt{x}", True),
    ],
)
def test_supported_delimiters(source: str, expression: str, display: bool) -> None:
    runs = parse_latex_runs(source)

    assert runs == [MathRun(expression, display, runs[0].source_syntax, runs[0].delimiter, 0, len(source))]


def test_text_formula_text_and_escaped_dollar() -> None:
    runs = parse_latex_runs(r"Price \$5 and $x^2$ now")

    assert isinstance(runs[0], TextRun)
    assert runs[0].text == "Price $5 and "
    assert isinstance(runs[1], MathRun)
    assert runs[1].expression == "x^2"
    assert runs[2].text == " now"


@pytest.mark.parametrize("source", ["$x", "$$x", r"\(x", r"\[x"])
def test_unclosed_delimiter_reports_position(source: str) -> None:
    with pytest.raises(ValueError, match="position 0"):
        parse_latex_runs(source)


def test_empty_formula_and_limits_are_rejected() -> None:
    with pytest.raises(ValueError, match="Empty"):
        parse_latex_runs("$$  $$")
    with pytest.raises(ValueError, match="max_expression_length"):
        parse_latex_runs("$abcd$", max_expression_length=3)
    with pytest.raises(ValueError, match="max_elements"):
        parse_latex_runs("$a$ $b$", max_elements=1)
