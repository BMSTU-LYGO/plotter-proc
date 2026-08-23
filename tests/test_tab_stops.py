from pathlib import Path

import pytest
import yaml
from PIL import Image

from plotter_processor.document_models import (
    SourceBBox,
    SourceDocument,
    SourcePage,
    SourceParagraph,
    SourceRasterImageElement,
    SourceTabStop,
    SourceTextElement,
    SourceTextRun,
)
from plotter_processor.document_paginator import paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.layout_models import PageTransform, RectMM
from plotter_processor.models import PageSpec
from tests.test_paragraph_layout import _layout


def _word_left(result, word_index: int) -> float:
    return min(glyph.x_mm for glyph in result.lines[0].glyphs if glyph.word_index == word_index)


def _word_right(result, word_index: int) -> float:
    return max(
        glyph.x_mm + glyph.advance_mm
        for glyph in result.lines[0].glyphs
        if glyph.word_index == word_index
    )


def test_custom_tab_stop_is_used(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("Key\tValue"),),
        left_indent_mm=5,
        tab_stops_mm=(30,),
        semantic_role="body",
    )
    result = _layout(paragraph, test_font)

    assert abs(_word_left(result, 1) - 45) < 0.01


def test_default_tab_stops_start_at_paragraph_left(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("Key\tValue"),), left_indent_mm=5, semantic_role="body"
    )
    result = _layout(paragraph, test_font)

    assert abs(_word_left(result, 1) - 27.5) < 0.01


@pytest.mark.parametrize("alignment", ["left", "center", "right", "decimal"])
def test_tab_alignment_uses_following_token_width(
    test_font: Path, alignment: str
) -> None:
    token = "12,34" if alignment == "decimal" else "Value"
    paragraph = SourceParagraph(
        (SourceTextRun(f"Key\t{token}"),),
        semantic_role="body",
        tab_stops=(SourceTabStop(30, alignment),),
    )

    result = _layout(paragraph, test_font)
    left = _word_left(result, 1)
    right = _word_right(result, 1)
    if alignment == "left":
        anchor = left
    elif alignment == "center":
        anchor = (left + right) / 2
    elif alignment == "right":
        anchor = right
    else:
        anchor = next(
            glyph.x_mm
            for glyph in result.lines[0].glyphs
            if glyph.word_index == 1 and glyph.char == ","
        )
    assert anchor == pytest.approx(40, abs=0.01)


def test_a4_to_a5_page_scale_applies_to_custom_tab_stop(test_font: Path) -> None:
    transform = PageTransform.create(
        210,
        297,
        RectMM(10, 10, 128, 190),
        source_content_rect=RectMM(20, 20, 170, 257),
    )
    paragraph = SourceParagraph(
        (SourceTextRun("Key\tValue"),),
        semantic_role="body",
        tab_stops=(SourceTabStop(40, "left"),),
    )

    result = _layout(paragraph, test_font, tab_scale=transform.scale)

    assert _word_left(result, 1) == pytest.approx(10 + 40 * transform.scale, abs=0.01)


def test_typed_tabs_keep_alignment_with_active_image_zone(
    tmp_path: Path, test_font: Path
) -> None:
    raster = tmp_path / "blank.png"
    Image.new("L", (10, 10), 255).save(raster)
    paragraph = SourceParagraph(
        (SourceTextRun("Key\tValue"),),
        semantic_role="body",
        tab_stops=(SourceTabStop(40, "right"),),
    )
    image = SourceRasterImageElement(
        "image", 0, 0, raster, 10, 10, 40, 40,
        SourceBBox(20, 20, 60, 60),
        anchor_type="anchored",
        wrap_mode="square",
        relative_to_h="page",
        relative_to_v="page",
    )
    text = SourceTextElement(
        "text", 1, 0, (paragraph.text,), styled_paragraphs=(paragraph,)
    )
    document = SourceDocument(
        tmp_path / "a4.docx",
        (SourcePage(0, 210, 297, (image, text), SourceBBox(20, 20, 190, 277)),),
    )
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))

    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("A5", 148, 210),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            document_layout_mode="hybrid",
            document_layout_options=config["document_layout"],
            paragraph_options=config["paragraphs"],
            preserve_source_page_breaks=False,
        )

    transform = result.layout_statistics["page_transform"]
    glyphs = [
        glyph
        for page in result.pages
        for glyph in page.layout.glyphs
        if glyph.word_index == 1
    ]
    right = max(glyph.x_mm + glyph.advance_mm for glyph in glyphs)
    assert right == pytest.approx(
        config["margins_mm"]["left"] + 40 * transform["scale"], abs=0.01
    )
