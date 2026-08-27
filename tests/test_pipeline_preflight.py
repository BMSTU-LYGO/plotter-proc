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


def test_selected_page_position_profile_is_checked_before_document_read(
    tmp_path: Path, test_font: Path, monkeypatch
) -> None:
    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))
    machine["page_position_profiles"]["A5"] = {
        "origin_x_mm": 100.0,
        "origin_y_mm": 20.0,
    }
    machine_path = tmp_path / "profile-outside-workspace.yaml"
    machine_path.write_text(yaml.safe_dump(machine), encoding="utf-8")
    options = _options(tmp_path, test_font, machine_path, output_name="profile")
    options.page = "A5"
    called = False

    def unexpected_read(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(pipeline, "read_structured_document", unexpected_read)

    result = run_pipeline(options)

    assert result.status == "error"
    assert not called
    assert result.error is not None
    assert "origin (100,20) mm" in result.error


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
    assert not (tmp_path / "compatible" / "extracted.txt").exists()
    assert not (tmp_path / "compatible" / "document-structure.json").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["artifact_level"] == "normal"
    assert "font_preview" not in report["outputs"]
    assert "extracted" not in report["outputs"]
    assert "document_structure" not in report["outputs"]


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
    assert (tmp_path / "debug" / "extracted.txt").exists()
    assert (tmp_path / "debug" / "document-structure.json").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["artifact_level"] == "debug"
    assert sum(report["cache"]["previews"].values()) == 1
    assert "extracted" in report["outputs"]
    assert "document_structure" in report["outputs"]


def test_minimal_artifact_level_omits_previews(
    tmp_path: Path, test_font: Path
) -> None:
    machine = _machine_config(tmp_path, max_y=320.0)
    options = _options(tmp_path, test_font, machine, output_name="minimal")
    options.artifact_level = "minimal"

    result = run_pipeline(options)

    assert result.status == "ok"
    assert not (options.output_dir / "plotter-preview.svg").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    job = json.loads((options.output_dir / "job.json").read_text(encoding="utf-8"))
    assert "plotter_preview" not in report["outputs"]
    assert job["pages"][0]["preview"] is None


def test_worker_count_is_bounded_by_memory_policy_and_page_count(monkeypatch) -> None:
    monkeypatch.setattr(pipeline.os, "cpu_count", lambda: 12)

    assert resolve_worker_count("auto", 20) == 4
    assert resolve_worker_count(8, 3) == 3
    assert resolve_worker_count(1, 20) == 1


def test_page_processes_preserve_order_and_output_bytes(
    tmp_path: Path, test_font: Path
) -> None:
    machine = _machine_config(tmp_path, max_y=320.0)
    sequential = _options(tmp_path, test_font, machine, output_name="workers-1")
    parallel = _options(tmp_path, test_font, machine, output_name="workers-2")
    sequential.input_path.write_text("parallel page " * 1400, encoding="utf-8")
    sequential.workers = 1
    parallel.workers = 2

    first = run_pipeline(sequential)
    second = run_pipeline(parallel)

    assert first.status == second.status == "ok"
    first_report = json.loads(first.report_path.read_text(encoding="utf-8"))
    second_report = json.loads(second.report_path.read_text(encoding="utf-8"))
    assert first_report["pagination"]["page_count"] >= 2
    assert [page["page"] for page in first_report["pages"]] == [
        page["page"] for page in second_report["pages"]
    ]
    assert (sequential.output_dir / "output.gcode").read_bytes() == (
        parallel.output_dir / "output.gcode"
    ).read_bytes()
    for page_number in range(1, first_report["pagination"]["page_count"] + 1):
        relative = Path("pages") / f"page-{page_number:03d}" / "paths.json"
        assert (sequential.output_dir / relative).read_bytes() == (
            parallel.output_dir / relative
        ).read_bytes()


def test_small_document_lazily_compiles_only_required_centerline_glyph(
    tmp_path: Path, test_font: Path
) -> None:
    machine = _machine_config(tmp_path, max_y=320.0)
    options = _options(tmp_path, test_font, machine, output_name="lazy-centerline")
    options.input_path.write_text("AAAA", encoding="utf-8")
    raw = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    raw["centerline"]["render"]["em_resolution_px"] = 512
    raw["centerline"]["render"]["padding_px"] = 16
    raw["centerline"]["skeleton"]["candidate_methods"] = ["skeletonize"]
    layout = tmp_path / "lazy-layout.yaml"
    layout.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cache = tmp_path / "lazy-cache" / "centerlines.json"
    options.layout_config_path = layout
    options.centerline_cache_path = cache
    options.font_mode = "centerline"
    options.connections = "off"
    options.workers = 1

    result = run_pipeline(options)

    assert result.status == "ok"
    manifest = json.loads((cache.parent / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert manifest["glyphs"] == ["A"]
    assert report["centerline"]["compiled_glyphs"] == 1
    assert report["centerline"]["cache_misses"] == 1
