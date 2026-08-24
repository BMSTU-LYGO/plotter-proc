import json
from pathlib import Path

import yaml

from plotter_processor import pipeline
from plotter_processor.pipeline import PipelineOptions, resolve_worker_count, run_pipeline


def _options(
    tmp_path: Path,
    test_font: Path,
    machine_config: Path,
    *,
    output_name: str,
) -> PipelineOptions:
    source = tmp_path / "input.txt"
    source.write_text("A4 preflight", encoding="utf-8")
    return PipelineOptions(
        input_path=source,
        font_path=test_font,
        page="A4",
        size="normal",
        layout_config_path=Path("configs/layout.yaml"),
        machine_config_path=machine_config,
        output_dir=tmp_path / output_name,
        page_numbers=False,
    )


def _machine_config(tmp_path: Path, *, max_y: float) -> Path:
    values = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))
    values["workspace_mm"]["max_y"] = max_y
    path = tmp_path / f"machine-{max_y}.yaml"
    path.write_text(yaml.safe_dump(values), encoding="utf-8")
    return path


def test_impossible_a4_fails_before_document_read(
    tmp_path: Path, test_font: Path, monkeypatch
) -> None:
    machine = _machine_config(tmp_path, max_y=220.0)
    called = False

    def unexpected_read(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("document read must not start before page/workspace preflight")

    monkeypatch.setattr(pipeline, "read_structured_document", unexpected_read)
    result = run_pipeline(
        _options(tmp_path, test_font, machine, output_name="impossible")
    )

    assert result.status == "error"
    assert not called
    assert result.error is not None
    assert "A4 portrait (210×297 mm)" in result.error
    assert "220×220 mm" in result.error
    assert "compatible machine config" in result.error


def test_a4_runs_with_a_compatible_workspace(tmp_path: Path, test_font: Path) -> None:
    machine = _machine_config(tmp_path, max_y=320.0)

    result = run_pipeline(
        _options(tmp_path, test_font, machine, output_name="compatible")
    )

    assert result.status == "ok"
    assert (tmp_path / "compatible" / "output.gcode").exists()
    assert (tmp_path / "compatible" / "plotter-preview.svg").exists()
    assert (tmp_path / "compatible" / "paths.json").exists()
    assert (tmp_path / "compatible" / "job.json").exists()
    assert not (tmp_path / "compatible" / "font-preview.svg").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["artifact_level"] == "normal"
    assert "font_preview" not in report["outputs"]


def test_debug_artifact_level_adds_font_and_subsystem_debug(
    tmp_path: Path, test_font: Path
) -> None:
    machine = _machine_config(tmp_path, max_y=320.0)
    options = _options(tmp_path, test_font, machine, output_name="debug")
    options.artifact_level = "debug"

    result = run_pipeline(options)

    assert result.status == "ok"
    assert (tmp_path / "debug" / "font-preview.svg").exists()
    assert (tmp_path / "debug" / "layout-debug").is_dir()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["artifact_level"] == "debug"
    assert sum(report["cache"]["previews"].values()) == 1


def test_worker_count_is_bounded_by_memory_policy_and_page_count(monkeypatch) -> None:
    monkeypatch.setattr(pipeline.os, "cpu_count", lambda: 12)

    assert resolve_worker_count("auto", 20) == 4
    assert resolve_worker_count(8, 3) == 3
    assert resolve_worker_count(1, 20) == 1
