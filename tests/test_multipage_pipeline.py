import json
from pathlib import Path

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def test_long_txt_writes_page_artifacts_and_job_gcode(tmp_path: Path, test_font: Path) -> None:
    source = tmp_path / "long.txt"
    source.write_text(
        "\n".join(["Long deterministic line of text 0123456789"] * 90),
        encoding="utf-8",
    )
    output = tmp_path / "build"
    result = run_pipeline(
        PipelineOptions(
            source,
            test_font,
            "A5",
            "normal",
            Path("configs/layout.yaml"),
            Path("configs/machine.yaml"),
            output,
            font_mode="outline",
            page_pause_seconds=90,
            park_corner="top_right",
        )
    )

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    page_count = report["pagination"]["page_count"]
    assert page_count > 1
    assert report["pagination"]["pause_count"] == page_count - 1
    assert report["motion"]["page_change_pause_time_seconds"] == 90 * (page_count - 1)
    assert (output / "job.json").is_file()
    assert (output / "plotter-preview.svg").is_file()
    for page_number in range(1, page_count + 1):
        page_dir = output / "pages" / f"page-{page_number:03d}"
        for filename in (
            "font-preview.svg",
            "plotter-preview.svg",
            "paths.json",
            "page.gcode",
            "report.json",
        ):
            assert (page_dir / filename).is_file()
        page_gcode = (page_dir / "page.gcode").read_text(encoding="utf-8")
        assert f"; Page {page_number}/{page_count}" in page_gcode
        assert "G4 P90000" not in page_gcode
        assert page_gcode.count("M84") == 1
        paths = json.loads((page_dir / "paths.json").read_text(encoding="utf-8"))
        assert any(stroke["element_type"] == "page-number" for stroke in paths["strokes"])
    job_gcode = (output / "output.gcode").read_text(encoding="utf-8")
    assert job_gcode.count("G4 P90000") == page_count - 1
    assert job_gcode.count("M84") == 1
    assert all(
        command not in job_gcode for command in ("M104", "M109", "M140", "M190", "G28")
    )


def test_no_paginate_keeps_overflow_error_and_removes_stale_gcode(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "long.txt"
    source.write_text("word " * 3000, encoding="utf-8")
    output = tmp_path / "build"
    output.mkdir()
    (output / "output.gcode").write_text("stale", encoding="utf-8")

    result = run_pipeline(
        PipelineOptions(
            source,
            test_font,
            "A5",
            "normal",
            Path("configs/layout.yaml"),
            Path("configs/machine.yaml"),
            output,
            paginate=False,
        )
    )

    assert result.status == "error"
    assert "does not fit" in (result.error or "")
    assert not list(output.rglob("*.gcode"))
