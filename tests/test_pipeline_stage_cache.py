import json
from pathlib import Path

import yaml

from plotter_processor import pipeline
from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _options(
    tmp_path: Path,
    test_font: Path,
    source: Path,
    output: str,
    *,
    machine_config: Path = Path("configs/machine.yaml"),
    layout_config: Path = Path("configs/layout.yaml"),
    page: str = "A5",
) -> PipelineOptions:
    return PipelineOptions(
        input_path=source,
        font_path=test_font,
        page=page,
        size="normal",
        layout_config_path=layout_config,
        machine_config_path=machine_config,
        output_dir=tmp_path / output,
        page_numbers=False,
        workers=1,
        stage_cache_path=tmp_path / "stage-cache",
    )


def test_document_and_layout_cache_reuse_and_invalidation(
    tmp_path: Path, test_font: Path, monkeypatch
) -> None:
    source = tmp_path / "input.txt"
    source.write_text("cached document", encoding="utf-8")
    calls = {"read": 0, "layout": 0, "geometry": 0}
    original_read = pipeline.read_structured_document
    original_layout = pipeline.paginate_document
    original_geometry = pipeline.process_page_geometry

    def counted_read(*args, **kwargs):
        calls["read"] += 1
        return original_read(*args, **kwargs)

    def counted_layout(*args, **kwargs):
        calls["layout"] += 1
        return original_layout(*args, **kwargs)

    def counted_geometry(*args, **kwargs):
        calls["geometry"] += 1
        return original_geometry(*args, **kwargs)

    monkeypatch.setattr(pipeline, "read_structured_document", counted_read)
    monkeypatch.setattr(pipeline, "paginate_document", counted_layout)
    monkeypatch.setattr(pipeline, "process_page_geometry", counted_geometry)

    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))
    machine["workspace_mm"]["max_y"] = 320
    compatible_machine = tmp_path / "machine-compatible.yaml"
    compatible_machine.write_text(yaml.safe_dump(machine), encoding="utf-8")

    first = run_pipeline(
        _options(
            tmp_path, test_font, source, "first", machine_config=compatible_machine
        )
    )
    second = run_pipeline(
        _options(
            tmp_path, test_font, source, "second", machine_config=compatible_machine
        )
    )

    assert first.status == second.status == "ok"
    assert calls == {"read": 1, "layout": 1, "geometry": 1}
    assert (tmp_path / "first" / "paths.json").read_bytes() == (
        tmp_path / "second" / "paths.json"
    ).read_bytes()
    second_report = json.loads(second.report_path.read_text(encoding="utf-8"))
    assert second_report["cache"]["stages"]["read_document"]["hits"] == 1
    assert second_report["cache"]["stages"]["layout"]["hits"] == 1
    assert second_report["cache"]["stages"]["geometry"]["hits"] == 1

    layout_entry = next((tmp_path / "stage-cache" / "layout").glob("*/entry.pickle"))
    layout_entry.write_bytes(b"damaged-layout-entry")
    repaired = run_pipeline(
        _options(
            tmp_path,
            test_font,
            source,
            "repaired-layout",
            machine_config=compatible_machine,
        )
    )
    assert repaired.status == "ok"
    assert calls == {"read": 1, "layout": 2, "geometry": 1}

    machine["feedrate_mm_min"]["travel"] += 100
    machine["motion_profiles"]["profiles"]["safe"]["feedrate_mm_min"][
        "travel"
    ] += 100
    changed_machine = tmp_path / "machine.yaml"
    changed_machine.write_text(yaml.safe_dump(machine), encoding="utf-8")
    machine_only = run_pipeline(
        _options(
            tmp_path,
            test_font,
            source,
            "machine-only",
            machine_config=changed_machine,
        )
    )
    assert machine_only.status == "ok"
    assert calls == {"read": 1, "layout": 2, "geometry": 1}
    assert (tmp_path / "first" / "paths.json").read_bytes() == (
        tmp_path / "machine-only" / "paths.json"
    ).read_bytes()
    assert (tmp_path / "first" / "output.gcode").read_bytes() != (
        tmp_path / "machine-only" / "output.gcode"
    ).read_bytes()

    different_page = run_pipeline(
        _options(
            tmp_path,
            test_font,
            source,
            "different-page",
            machine_config=compatible_machine,
            page="A4",
        )
    )
    assert different_page.status == "ok"
    assert calls == {"read": 1, "layout": 3, "geometry": 2}

    layout_values = yaml.safe_load(
        Path("configs/layout.yaml").read_text(encoding="utf-8")
    )
    layout_values["handwriting"]["variation"]["enabled"] = True
    layout_values["handwriting"]["variation"]["seed"] += 1
    changed_handwriting = tmp_path / "layout-handwriting.yaml"
    changed_handwriting.write_text(
        yaml.safe_dump(layout_values, allow_unicode=True), encoding="utf-8"
    )
    handwriting_only = run_pipeline(
        _options(
            tmp_path,
            test_font,
            source,
            "handwriting-only",
            machine_config=compatible_machine,
            layout_config=changed_handwriting,
        )
    )
    assert handwriting_only.status == "ok"
    assert calls == {"read": 1, "layout": 3, "geometry": 3}

    source.write_text("changed cached document", encoding="utf-8")
    changed_source = run_pipeline(
        _options(
            tmp_path,
            test_font,
            source,
            "changed-source",
            machine_config=compatible_machine,
        )
    )
    assert changed_source.status == "ok"
    assert calls == {"read": 2, "layout": 4, "geometry": 4}
