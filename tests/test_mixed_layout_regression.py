import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from plotter_processor.document_models import (
    SourceBBox,
    SourceDocument,
    SourcePage,
    SourceRasterImageElement,
    SourceTextElement,
)
from plotter_processor.document_paginator import paginate_document
from plotter_processor.docx_document_reader import read_docx_document
from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec
from plotter_processor.pipeline import resolve_document_layout_mode


def _config() -> dict[str, object]:
    return yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))


def _image(path: Path) -> None:
    image = Image.new("RGB", (80, 50), "white")
    ImageDraw.Draw(image).line((3, 3, 76, 46), fill="black", width=4)
    image.save(path)


def test_future_paragraph_image_zone_activates_at_source_order(
    tmp_path: Path, test_font: Path
) -> None:
    config = _config()
    image_path = tmp_path / "image.png"
    _image(image_path)
    before = SourceTextElement(
        "before", 0, 0, ("Before image text keeps its normal flow and line spacing. " * 3,)
    )
    image = SourceRasterImageElement(
        "future-image",
        1,
        0,
        image_path,
        80,
        50,
        25.0,
        15.625,
        SourceBBox(45, 10, 70, 25.625),
        "anchored",
        "square",
        "both",
        relative_to_h="margin",
        relative_to_v="paragraph",
    )
    after = SourceTextElement("after", 2, 0, ("After image text. " * 20,))
    document = SourceDocument(
        tmp_path / "mixed.docx", (SourcePage(0, 80, 80, (before, image, after)),)
    )
    debug = tmp_path / "layout-debug"

    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("test", 80, 80),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            image_mode="centerline",
            document_layout_mode="preserve",
            document_layout_options=config["document_layout"],
            layout_debug_dir=debug,
            preserve_source_page_breaks=False,
        )

    trace = json.loads((debug / "trace.json").read_text(encoding="utf-8"))["events"]
    before_event = next(event for event in trace if event["element_id"] == "before")
    image_event = next(event for event in trace if event["element_id"] == "future-image")
    assert before_event["active_exclusion_zones"] == []
    assert image_event["placement_reason"] == "activated_at_source_order"
    assert sum("future-image" in page.source_element_ids for page in result.pages) == 1
    assert result.layout_statistics["unexplained_vertical_gap_count"] == 0


def test_zones_are_not_carried_to_a_new_page(tmp_path: Path, test_font: Path) -> None:
    config = _config()
    image_path = tmp_path / "image.png"
    _image(image_path)
    image = SourceRasterImageElement(
        "image",
        0,
        0,
        image_path,
        80,
        50,
        24.0,
        15.0,
        SourceBBox(45, 12, 69, 27),
        "anchored",
        "square",
        "both",
        relative_to_v="paragraph",
    )
    text = SourceTextElement("text", 1, 0, ("Long flowing paragraph. " * 90,))
    document = SourceDocument(
        tmp_path / "pages.docx", (SourcePage(0, 80, 80, (image, text)),)
    )

    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("test", 80, 80),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            image_mode="centerline",
            document_layout_mode="hybrid",
            document_layout_options=config["document_layout"],
            layout_debug_dir=tmp_path / "layout-debug",
            preserve_source_page_breaks=False,
        )

    assert len(result.pages) >= 3
    assert sum("image" in page.source_element_ids for page in result.pages) == 1
    second_page_first_line = result.pages[1].metadata["line_boxes"][0]
    assert second_page_first_line["x"] == config["margins_mm"]["left"]


def test_auto_layout_defaults_by_document_type() -> None:
    assert resolve_document_layout_mode(Path("input.txt"), None, "auto") == "reflow"
    assert resolve_document_layout_mode(Path("input.docx"), None, "auto") == "hybrid"
    assert resolve_document_layout_mode(Path("input.pdf"), None, "auto") == "hybrid"
    assert resolve_document_layout_mode(Path("input.pdf"), "preserve", "auto") == "preserve"


def test_mixed_fixture_keeps_images_formulas_and_multipage_order(
    tmp_path: Path, test_font: Path
) -> None:
    config = _config()
    document = read_docx_document(
        Path("tests/fixtures/layout/mixed_layout_demo.docx"), tmp_path / "assets"
    )

    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("A4", 210, 297),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            image_mode="centerline",
            latex_mode="auto",
            latex_options=config["latex"],
            latex_stroke_mode="centerline",
            document_layout_mode="hybrid",
            document_layout_options=config["document_layout"],
            layout_debug_dir=tmp_path / "mixed-layout-debug",
            preserve_source_page_breaks=False,
        )

    image_ids = [
        item["id"] for item in result.layout_statistics["elements"]
        if item["element_type"] == "raster-image"
    ]
    assert len(result.pages) >= 2
    assert len(image_ids) == len(set(image_ids)) == 2
    assert result.latex_statistics["inline_expressions"] == 1
    assert result.latex_statistics["block_expressions"] == 1
    assert result.layout_statistics["overlaps_remaining"] == 0
    assert result.layout_statistics["unexplained_vertical_gap_count"] == 0
