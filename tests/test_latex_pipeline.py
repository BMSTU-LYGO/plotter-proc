import json
from pathlib import Path

import yaml

from plotter_processor.composition_pipeline import compose_manifest
from plotter_processor.pipeline import PipelineOptions, run_pipeline


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


def test_strict_latex_quality_aborts_before_gcode(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "strict-formula.txt"
    source.write_text(r"Formula: $x+y+z$", encoding="utf-8")
    layout = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    layout["latex"]["max_components"] = 1
    layout["latex"]["fallback_to_outline"] = True
    layout_path = tmp_path / "strict-layout.yaml"
    layout_path.write_text(yaml.safe_dump(layout), encoding="utf-8")
    output = tmp_path / "strict-output"

    result = run_pipeline(PipelineOptions(
        input_path=source,
        font_path=test_font,
        page="A5",
        size="normal",
        layout_config_path=layout_path,
        machine_config_path=Path("configs/machine.yaml"),
        output_dir=output,
        page_numbers=False,
        latex="mathtext",
        strict_latex_quality=True,
    ))

    assert result.status == "error"
    assert result.error is not None
    assert "components" in result.error or "quality gate" in result.error
    assert not list(output.rglob("*.gcode"))
