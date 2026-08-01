import json
from pathlib import Path

import fitz

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def test_pdf_preserve_maps_raster_bbox_without_displacement(
    tmp_path: Path, test_font: Path
) -> None:
    output = tmp_path / "preserve"
    result = run_pipeline(PipelineOptions(
        Path("tests/fixtures/update_7/images/image_preserve_position.pdf"),
        test_font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        images="centerline",
        document_layout="preserve",
        pdf_math="off",
        page_numbers=False,
    ))

    assert result.status == "ok", result.error
    layout = json.loads((output / "report.json").read_text())["document_layout"]
    assert layout["mean_center_displacement_mm"] == 0
    assert layout["overlaps_remaining"] == 0
    assert layout["page_overflow_area_mm2"] == 0


def test_pdf_vector_uses_preserve_mapping(tmp_path: Path, test_font: Path) -> None:
    source = tmp_path / "vector.pdf"
    document = fitz.open()
    page = document.new_page(width=420, height=595)
    page.draw_rect(fitz.Rect(250, 100, 350, 180), width=2)
    document.save(source)
    document.close()
    output = tmp_path / "vector-output"

    result = run_pipeline(PipelineOptions(
        source,
        test_font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        document_layout="preserve",
        pdf_math="off",
        page_numbers=False,
    ))

    assert result.status == "ok", result.error
    layout = json.loads((output / "report.json").read_text())["document_layout"]
    assert layout["elements"][0]["element_type"] == "pdf-vector"
    assert layout["mean_center_displacement_mm"] == 0
