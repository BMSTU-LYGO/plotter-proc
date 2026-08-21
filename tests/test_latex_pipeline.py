import json
from pathlib import Path

from plotter_processor.composition_pipeline import compose_manifest


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
