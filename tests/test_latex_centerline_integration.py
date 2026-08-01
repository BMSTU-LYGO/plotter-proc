import json
import re
from pathlib import Path

from plotter_processor.latex_renderer import math_renderer_from_options
from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _options(source: Path, output: Path, font: Path) -> PipelineOptions:
    return PipelineOptions(
        source,
        font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        font_mode="outline",
        latex_stroke_mode="centerline",
        strict_latex_quality=True,
    )


def test_centerline_formula_reaches_safe_gcode(tmp_path: Path, test_font: Path) -> None:
    source = tmp_path / "formula.txt"
    source.write_text(r"Text $\frac{a}{b}+x^2$", encoding="utf-8")
    output = tmp_path / "job"

    result = run_pipeline(_options(source, output, test_font))

    assert result.status == "ok", result.error
    paths = json.loads((output / "paths.json").read_text(encoding="utf-8"))
    formulas = [stroke for stroke in paths["strokes"] if stroke["element_type"] == "latex"]
    assert formulas
    assert all(stroke["semantic_role"] == "latex-centerline" for stroke in formulas)
    gcode = (output / "output.gcode").read_text(encoding="utf-8")
    assert all(command not in gcode for command in ("M104", "M109", "M140", "M190", "G28"))
    assert not re.search(r"(?m)^(?:G0|G1).*\sE-?\d", gcode)


def test_formula_error_removes_stale_gcode(tmp_path: Path, test_font: Path) -> None:
    source = tmp_path / "bad.txt"
    source.write_text(r"$\unsupportedcommand{x}$", encoding="utf-8")
    output = tmp_path / "bad-job"
    output.mkdir()
    (output / "output.gcode").write_text("stale", encoding="utf-8")

    result = run_pipeline(_options(source, output, test_font))

    assert result.status == "error"
    assert "MathText cannot render" in (result.error or "")
    assert not (output / "output.gcode").exists()


def test_old_latex_config_uses_centerline_defaults() -> None:
    renderer = math_renderer_from_options({"curve_tolerance_mm": 0.04})

    assert renderer.stroke_mode == "centerline"
    assert renderer.render_ppmm == 24.0
