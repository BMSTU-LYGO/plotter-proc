import json
from pathlib import Path

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def test_hybrid_text_lines_do_not_enter_image_zone(tmp_path: Path, test_font: Path) -> None:
    output = tmp_path / "hybrid"
    result = run_pipeline(PipelineOptions(
        Path("tests/fixtures/update_7/images/image_left_wrap.docx"),
        test_font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        images="centerline",
        document_layout="hybrid",
        layout_debug=True,
        page_numbers=False,
    ))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["document_layout"]["overlaps_remaining"] == 0
    assert report["document_layout"]["images_wrapped"] == 1
