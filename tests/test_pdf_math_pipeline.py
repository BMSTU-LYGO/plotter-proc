import json
from pathlib import Path

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _options(source: Path, output: Path, font: Path, *, pdf_math: str) -> PipelineOptions:
    return PipelineOptions(
        source,
        font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        font_mode="outline",
        pdf_math=pdf_math,
        math_debug=True,
    )


def test_pdf_visual_formula_is_centerlined_once(tmp_path: Path, test_font: Path) -> None:
    source = Path("tests/fixtures/update_7/latex/pdf_formula_text.pdf")
    output = tmp_path / "visual"

    result = run_pipeline(_options(source, output, test_font, pdf_math="auto"))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["latex"]["pdf_visual_expressions"] == 1
    paths = json.loads((output / "paths.json").read_text(encoding="utf-8"))
    formulas = [stroke for stroke in paths["strokes"] if stroke["element_type"] == "latex"]
    assert formulas
    assert all(stroke["segment_types"] == ["latex-centerline"] for stroke in formulas)
    structure = json.loads((output / "document-structure.json").read_text(encoding="utf-8"))
    elements = structure["pages"][0]["elements"]
    assert sum(element["type"] == "math" for element in elements) == 1
    assert not any(
        "x^2 + y^2 = z^2" in " ".join(element.get("paragraphs", []))
        for element in elements
    )
    assert (output / "latex-debug" / "formula-001-pdf-clip.png").is_file()
    assert (output / "latex-debug" / "formula-001-overlay.svg").is_file()


def test_pdf_math_off_keeps_old_text_pipeline(tmp_path: Path, test_font: Path) -> None:
    source = Path("tests/fixtures/update_7/latex/pdf_formula_text.pdf")
    output = tmp_path / "off"

    result = run_pipeline(_options(source, output, test_font, pdf_math="off"))

    if result.status == "ok":
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        assert report["latex"]["pdf_visual_expressions"] == 0
    else:
        assert "missing required glyph" in (result.error or "")
        assert not (output / "output.gcode").exists()
