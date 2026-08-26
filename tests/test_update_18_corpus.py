import json
from pathlib import Path
from xml.etree import ElementTree

from plotter_processor.document_models import (
    SourceArrowElement,
    SourceMathElement,
    SourceRasterImageElement,
    SourceTableElement,
    SourceTextElement,
    SourceVectorElement,
)
from plotter_processor.latex_parser import MathRun, parse_latex_runs
from plotter_processor.pipeline import PipelineOptions, _math_report, run_pipeline
from plotter_processor.structured_document_reader import read_structured_document

CORPUS = Path("tests/fixtures/update_18")


def test_update_18_compact_math_report_distinguishes_sources_and_fallbacks() -> None:
    report = _math_report({
        "cache_hits": 2,
        "glyph_cache_hits": 3,
        "formulas": [
            {"source_syntax": "latex", "quality": {"render_path": "vector-first"}},
            {"source_syntax": "omml", "quality": {"render_path": "vector-first"}},
            {"source_syntax": "pdf-visual", "quality": {}},
            {
                "source_syntax": "latex",
                "warnings": ["latex_vector_raster_fallback"],
                "quality": {"quality_failures": ["branch-loss"]},
            },
        ],
    })

    assert report == {
        "formulas_total": 4,
        "latex": 2,
        "omml": 1,
        "pdf_visual": 1,
        "vector_rendered": 2,
        "raster_fallback": 1,
        "vector_first_ratio": 0.5,
        "cache_hits": 5,
        "warnings": 1,
        "quality_failures": 1,
    }


def test_update_18_latex_and_preview_corpus_is_complete() -> None:
    text = (CORPUS / "latex_corpus.txt").read_text(encoding="utf-8")
    formulas = [run for run in parse_latex_runs(text) if isinstance(run, MathRun)]
    preview = ElementTree.parse(CORPUS / "canonical_math_preview.svg").getroot()

    assert len(formulas) >= 10
    expressions = "\n".join(run.expression for run in formulas)
    assert all(marker in expressions for marker in (
        r"\frac", r"\sqrt", r"\int", r"\sum", r"\lim", r"\begin{pmatrix}",
        r"\begin{cases}", r"\begin{aligned}",
    ))
    assert preview.tag.endswith("svg")
    assert list(preview)


def test_update_18_docx_corpus_has_mixed_semantic_objects(tmp_path: Path) -> None:
    document = read_structured_document(
        CORPUS / "complex_math_document.docx",
        assets_dir=tmp_path / "docx-assets",
    )

    assert any(isinstance(item, SourceMathElement) for item in document.elements)
    assert any(isinstance(item, SourceTableElement) for item in document.elements)
    assert any(isinstance(item, SourceRasterImageElement) for item in document.elements)
    assert any(isinstance(item, SourceVectorElement) for item in document.elements)
    assert any(isinstance(item, SourceArrowElement) for item in document.elements)
    assert any(
        isinstance(item, SourceTextElement)
        and any("Flow" in paragraph for paragraph in item.paragraphs)
        for item in document.elements
    )


def test_update_18_pdf_and_svg_corpus_preserve_math_and_vectors(tmp_path: Path) -> None:
    pdf = read_structured_document(
        CORPUS / "mixed_math_diagram.pdf",
        assets_dir=tmp_path / "pdf-assets",
        pdf_math_mode="auto",
    )
    svg = read_structured_document(CORPUS / "vector_diagram.svg")

    assert any(isinstance(item, SourceMathElement) for item in pdf.elements)
    assert any(isinstance(item, SourceTextElement) for item in pdf.elements)
    assert any(isinstance(item, SourceVectorElement) for item in pdf.elements)
    assert svg.metadata.source_format == "svg"
    assert all(isinstance(item, SourceVectorElement) for item in svg.elements)


def test_update_18_math_audit_report_is_vector_first_and_safe(
    tmp_path: Path, test_font: Path
) -> None:
    output = tmp_path / "latex-audit"
    result = run_pipeline(PipelineOptions(
        input_path=CORPUS / "latex_corpus.txt",
        font_path=test_font,
        page="A5",
        size="normal",
        layout_config_path=Path("configs/layout.yaml"),
        machine_config_path=Path("configs/machine.yaml"),
        output_dir=output,
        page_numbers=False,
        latex="mathtext",
        strict_latex_quality=True,
        artifact_level="audit",
    ))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    math = report["math"]
    assert math["formulas_total"] >= 10
    assert math["vector_rendered"] == math["formulas_total"]
    assert math["raster_fallback"] == 0
    assert math["quality_failures"] == 0
    assert math["vector_first_ratio"] == 1.0
    paths = json.loads((output / "paths.json").read_text(encoding="utf-8"))
    assert all(
        0 <= x <= 148 and 0 <= y <= 210
        for stroke in paths["strokes"]
        for x, y in stroke["points"]
    )
