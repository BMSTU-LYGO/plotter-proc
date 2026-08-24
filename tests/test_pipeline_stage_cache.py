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
) -> PipelineOptions:
    return PipelineOptions(
        input_path=source,
        font_path=test_font,
        page="A5",
        size="normal",
        layout_config_path=Path("configs/layout.yaml"),
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
    calls = {"read": 0, "layout": 0}
    original_read = pipeline.read_structured_document
    original_layout = pipeline.paginate_document

    def counted_read(*args, **kwargs):
        calls["read"] += 1
        return original_read(*args, **kwargs)

    def counted_layout(*args, **kwargs):
        calls["layout"] += 1
        return original_layout(*args, **kwargs)

    monkeypatch.setattr(pipeline, "read_structured_document", counted_read)
    monkeypatch.setattr(pipeline, "paginate_document", counted_layout)

    first = run_pipeline(_options(tmp_path, test_font, source, "first"))
    second = run_pipeline(_options(tmp_path, test_font, source, "second"))

    assert first.status == second.status == "ok"
    assert calls == {"read": 1, "layout": 1}
    assert (tmp_path / "first" / "paths.json").read_bytes() == (
        tmp_path / "second" / "paths.json"
    ).read_bytes()
    second_report = json.loads(second.report_path.read_text(encoding="utf-8"))
    assert second_report["cache"]["stages"]["read_document"]["hits"] == 1
    assert second_report["cache"]["stages"]["layout"]["hits"] == 1

    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))
    machine["feedrate_mm_min"]["travel"] += 100
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
    assert calls == {"read": 1, "layout": 1}

    source.write_text("changed cached document", encoding="utf-8")
    changed_source = run_pipeline(_options(tmp_path, test_font, source, "changed-source"))
    assert changed_source.status == "ok"
    assert calls == {"read": 2, "layout": 2}
