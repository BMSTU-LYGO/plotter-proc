import json
from pathlib import Path

import pytest
from docx import Document

from plotter_processor.pipeline import PipelineOptions, run_pipeline


@pytest.mark.parametrize(
    ("fixture", "side"),
    [("image_left_wrap.docx", "left"), ("image_right_wrap.docx", "right")],
)
def test_hybrid_preserves_side_and_aspect_ratio(
    tmp_path: Path, test_font: Path, fixture: str, side: str
) -> None:
    output = tmp_path / side
    result = run_pipeline(PipelineOptions(
        Path("tests/fixtures/update_7/images") / fixture,
        test_font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        images="centerline",
        document_layout="hybrid",
        page_numbers=False,
    ))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    placement = report["document_layout"]["elements"][0]
    bbox = placement["output_bbox_mm"]
    center = bbox["x"] + bbox["width"] / 2
    assert (center < 74) if side == "left" else (center > 74)
    assert abs(bbox["width"] / bbox["height"] - 1.5) < 0.005
    assert report["document_layout"]["max_center_displacement_mm"] <= 10
    assert report["document_layout"]["overlaps_remaining"] == 0


def test_hybrid_top_bottom_advances_text_below_image(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "top-bottom.docx"
    document = Document("tests/fixtures/update_7/images/image_top_bottom.docx")
    for paragraph in document.paragraphs:
        if "_" in paragraph.text:
            paragraph.text = paragraph.text.replace("_", " ")
    document.save(source)
    output = tmp_path / "top-bottom"
    result = run_pipeline(PipelineOptions(
        source,
        test_font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        images="centerline",
        document_layout="hybrid",
        page_numbers=False,
    ))

    assert result.status == "ok", result.error
    layout = json.loads((output / "report.json").read_text())["document_layout"]
    assert layout["images_top_bottom"] == 1
    assert layout["overlaps_remaining"] == 0
