from pathlib import Path

import pytest
import yaml

from plotter_processor.document_models import SourceDocument, SourcePage, SourceTextElement
from plotter_processor.document_paginator import paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.latex_renderer import MathTextRenderer
from plotter_processor.math_expression import normalize_latex_expression
from plotter_processor.models import PageSpec


@pytest.mark.parametrize(
    ("environment", "expected_delimiters"),
    [
        ("matrix", 0),
        ("pmatrix", 2),
        ("bmatrix", 2),
        ("Bmatrix", 2),
        ("vmatrix", 2),
        ("Vmatrix", 4),
    ],
)
def test_matrix_layout_has_rows_columns_and_analytic_delimiters(
    environment: str, expected_delimiters: int
) -> None:
    expression = rf"\begin{{{environment}}}a&b\\c&d\end{{{environment}}}"
    rendered = MathTextRenderer().render(expression, 5.0)
    structural = [
        stroke for stroke in rendered.strokes
        if stroke.segment_types == ("latex-structural-delimiter",)
    ]

    assert rendered.quality["render_path"] == "vector-first"
    assert rendered.quality["rows"] == 2
    assert rendered.quality["columns"] == 2
    assert len(structural) == expected_delimiters
    assert rendered.quality["quality_failures"] == ()


def test_cases_and_aligned_have_normalized_row_models() -> None:
    cases = r"\begin{cases}x^2&x\geq0\\-x&x<0\end{cases}"
    aligned = r"\begin{aligned}x+y&=10\\2x-y&=5\end{aligned}"

    cases_model = normalize_latex_expression(cases)
    aligned_model = normalize_latex_expression(aligned)
    cases_rendered = MathTextRenderer().render(cases_model, 5.0)
    aligned_rendered = MathTextRenderer().render(aligned_model, 5.0)

    assert cases_model.root.kind == "cases"
    assert len(cases_model.root.children) == 2
    assert all(len(row.children) == 2 for row in cases_model.root.children)
    assert cases_rendered.quality["structural_lines"] == 1
    assert aligned_model.root.kind == "aligned"
    assert aligned_rendered.quality["rows"] == 2
    assert aligned_rendered.quality["columns"] == 2


def test_multiline_formula_paginates_as_one_object(test_font: Path) -> None:
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    expression = r"$$\begin{pmatrix}1&2\\3&4\end{pmatrix}$$"
    document = SourceDocument(
        Path("matrix.txt"),
        (SourcePage(0, None, None, (
            SourceTextElement("matrix", 0, 0, ("Line one", "Line two", "Line three", expression)),
        )),),
    )
    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("small", 80.0, 58.0),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            latex_mode="mathtext",
            latex_options=config["latex"],
            preserve_source_page_breaks=False,
        )

    formula_pages = [page for page in result.pages if page.metadata["formulas"]]
    assert len(formula_pages) == 1
    assert formula_pages[0].page_index > 0
    assert formula_pages[0].metadata["formulas"][0]["expression"] == expression[2:-2]
