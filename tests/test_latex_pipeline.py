import json
import re
from pathlib import Path

from plotter_processor.composition_pipeline import compose_manifest
from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _options(source: Path, output: Path, font: Path, *, latex: str = "mathtext") -> PipelineOptions:
    return PipelineOptions(
        source, font, "A5", "normal", Path("configs/layout.yaml"),
        Path("configs/machine.yaml"), output, font_mode="outline",
        latex=latex, latex_debug=True,
    )


def test_latex_reaches_preview_paths_gcode_report_and_debug(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "latex.txt"
    source.write_text(
        "Formula: $(a+b)^2 = a^2 + 2ab + b^2$.\n\n"
        "$$\\int_0^1 x^2 dx = \\frac{1}{3}$$",
        encoding="utf-8",
    )
    output = tmp_path / "build"

    result = run_pipeline(_options(source, output, test_font))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["latex"]["expressions_found"] == 2
    assert report["latex"]["inline_expressions"] == 1
    assert report["latex"]["block_expressions"] == 1
    paths = json.loads((output / "paths.json").read_text(encoding="utf-8"))
    assert any(stroke["element_type"] == "latex" for stroke in paths["strokes"])
    assert "data-element-type=\"latex\"" in (output / "plotter-preview.svg").read_text()
    assert (output / "latex-debug" / "formula-001.svg").is_file()
    assert (output / "latex-debug" / "formula-002.json").is_file()
    gcode = (output / "output.gcode").read_text(encoding="utf-8")
    assert all(command not in gcode for command in ("M104", "M109", "M140", "M190", "G28"))
    assert not re.search(r"(?m)^(?:G0|G1).*\sE-?\d", gcode)


def test_multiline_block_formula_from_txt_is_rendered(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "multiline.txt"
    source.write_text("Before\n\n$$\n\\frac{a}{b}\n$$\n\nAfter", encoding="utf-8")
    output = tmp_path / "build"

    result = run_pipeline(_options(source, output, test_font))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["latex"]["block_expressions"] == 1


def test_block_formula_moves_atomically_to_a_later_page(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "paginated.txt"
    source.write_text("A\n" * 40 + "$$\\frac{a}{b}$$", encoding="utf-8")
    output = tmp_path / "build"

    result = run_pipeline(_options(source, output, test_font))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["pagination"]["page_count"] > 1
    pages_with_formula = 0
    for paths_file in sorted((output / "pages").glob("page-*/paths.json")):
        paths = json.loads(paths_file.read_text(encoding="utf-8"))
        pages_with_formula += any(
            stroke["element_type"] == "latex" for stroke in paths["strokes"]
        )
    assert pages_with_formula == 1


def test_latex_off_is_literal_and_deterministic(tmp_path: Path, test_font: Path) -> None:
    source = tmp_path / "literal.txt"
    source.write_text("Literal $x$", encoding="utf-8")
    first = run_pipeline(_options(source, tmp_path / "first", test_font, latex="off"))
    second = run_pipeline(_options(source, tmp_path / "second", test_font, latex="off"))

    assert first.status == second.status
    if first.status == "ok":
        first_paths = json.loads((tmp_path / "first" / "paths.json").read_text())
        assert not any(stroke["element_type"] == "latex" for stroke in first_paths["strokes"])
    else:
        assert first.error == second.error


def test_latex_in_composition_text_reaches_vector_outputs(
    tmp_path: Path, test_font: Path
) -> None:
    manifest = tmp_path / "formula.plotter.yaml"
    manifest.write_text(
        "version: 1\n"
        "page: A5\n"
        f"fonts:\n  primary: {test_font}\n"
        "elements:\n"
        "  - id: formula\n"
        "    type: text\n"
        "    text: 'Area: $\\pi r^2$'\n"
        "    x_mm: 10\n"
        "    y_mm: 10\n"
        "    width_mm: 100\n"
        "    size: normal\n"
        "    font_mode: outline\n",
        encoding="utf-8",
    )
    output = tmp_path / "composition"

    result = compose_manifest(manifest, output, latex="mathtext", latex_debug=True)

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["composition"]["latex"]["expressions_found"] == 1
    paths = json.loads((output / "paths.json").read_text(encoding="utf-8"))
    assert any(stroke["element_type"] == "latex" for stroke in paths["strokes"])
    assert (output / "latex-debug" / "formula-001.svg").is_file()
