import json
from pathlib import Path

import pytest

from plotter_processor.pipeline import PipelineOptions, run_pipeline


@pytest.mark.parametrize(
    ("fixture", "key", "minimum"),
    [("underline_runs.docx", "underlines", 4), ("arrows.docx", "arrows", 1), ("simple_table.docx", "tables", 1), ("simple_table.pdf", "tables", 1), ("arrows.pdf", "arrows", 2), ("underline_pdf.pdf", "underlines", 1)],
)
def test_semantic_fixture_reaches_paths_report_and_safe_gcode(tmp_path: Path, test_font: Path, fixture: str, key: str, minimum: int) -> None:
    source = Path("tests/fixtures/update_7/lines_tables") / fixture
    output = tmp_path / fixture
    result = run_pipeline(PipelineOptions(source, test_font, "A5", "normal", Path("configs/layout.yaml"), Path("configs/machine.yaml"), output, pdf_math="off", page_numbers=False, semantic_debug=True))
    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text())
    assert report["semantic_objects"][key] >= minimum
    gcode = (output / "output.gcode").read_text()
    assert all(command not in gcode for command in ("M104", "M109", "M140", "M190", "G28"))
    assert (output / "semantic-debug" / "classification.json").is_file()


def test_multipage_table_splits_only_between_rows(tmp_path: Path, test_font: Path) -> None:
    output = tmp_path / "multipage"
    result = run_pipeline(PipelineOptions(Path("tests/fixtures/update_7/lines_tables/multipage_table.docx"), test_font, "A5", "normal", Path("configs/layout.yaml"), Path("configs/machine.yaml"), output, page_numbers=True))
    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text())
    assert report["semantic_objects"]["table_pages"] >= 2
    job = json.loads((output / "job.json").read_text())
    assert len(job["pages"]) >= 2
    assert job["pages"][1]["metadata"]["table_fragments"][0]["rows"][0] == 0
