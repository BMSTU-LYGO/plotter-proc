import json
from pathlib import Path

import pytest
from docx import Document

from plotter_processor.pipeline import PipelineOptions, run_pipeline

FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def require_test_font() -> Path:
    if not FONT_PATH.is_file():
        pytest.skip("System test font is unavailable")
    return FONT_PATH


def _create_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("Привет, это небольшой тест. 0123456789")
    document.save(path)


def test_runs_complete_pipeline_and_writes_report(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "build"
    _create_docx(source)

    result = run_pipeline(
        PipelineOptions(
            input_path=source,
            font_path=require_test_font(),
            page="A5",
            size="normal",
            layout_config_path=Path("configs/layout.yaml"),
            machine_config_path=Path("configs/machine.yaml"),
            output_dir=output,
        )
    )

    assert result.status == "ok", result.error
    for filename in (
        "extracted.txt",
        "font-preview.svg",
        "plotter-preview.svg",
        "paths.json",
        "output.gcode",
        "report.json",
    ):
        assert (output / filename).is_file()
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["pipeline"] == "ttf-vector"
    assert report["statistics"]["characters"] > 0
    assert report["statistics"]["strokes"] > 0
    assert "G28" not in (output / "output.gcode").read_text(encoding="utf-8")
    assert not (output / "page.png").exists()
    assert not (output / "skeleton.png").exists()


def test_error_report_removes_existing_gcode(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "build"
    output.mkdir()
    (output / "output.gcode").write_text("unsafe stale file", encoding="utf-8")
    _create_docx(source)

    result = run_pipeline(
        PipelineOptions(
            input_path=source,
            font_path=tmp_path / "missing.ttf",
            page="A5",
            size="normal",
            layout_config_path=Path("configs/layout.yaml"),
            machine_config_path=Path("configs/machine.yaml"),
            output_dir=output,
        )
    )

    assert result.status == "error"
    assert not (output / "output.gcode").exists()
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "error"
    assert "Font file does not exist" in report["error"]
