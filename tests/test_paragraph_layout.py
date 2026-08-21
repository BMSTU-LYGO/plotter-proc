from pathlib import Path

import yaml

from plotter_processor.document_models import (
    SourceDocument,
    SourcePage,
    SourceParagraph,
    SourceTextElement,
    SourceTextRun,
)
from plotter_processor.document_paginator import paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec
from plotter_processor.paragraph_layout import layout_paragraph


def _layout(paragraph: SourceParagraph, test_font: Path, *, right: float = 70):
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    with load_font(test_font) as font:
        return layout_paragraph(
            paragraph,
            font,
            content_left_mm=10,
            content_right_mm=right,
            base_size_options=config["sizes"]["normal"],
            paragraph_options=config["paragraphs"],
        )


def test_first_line_left_and_right_indents_apply_to_line_boxes(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("word " * 30),),
        first_line_indent_mm=8,
        left_indent_mm=4,
        right_indent_mm=6,
        semantic_role="body",
    )
    result = _layout(paragraph, test_font)

    assert len(result.lines) > 1
    assert result.lines[0].left_mm == 22
    assert all(line.left_mm == 14 for line in result.lines[1:])
    assert all(line.right_mm == 64 for line in result.lines)


def test_hanging_indent_is_not_first_line_indent(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("1. long list item " * 10),),
        hanging_indent_mm=5,
        left_indent_mm=8,
        semantic_role="body",
    )
    result = _layout(paragraph, test_font)

    assert result.lines[0].left_mm == 13
    assert result.lines[1].left_mm == 18


def test_heading_scale_and_spacing_are_clamped(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("Heading"),),
        semantic_role="heading_1",
        space_before_mm=99,
        space_after_mm=99,
    )
    result = _layout(paragraph, test_font)

    assert result.font_scale == 1.25
    assert result.space_before_mm == 12
    assert result.space_after_mm == 12


def test_target_page_break_keeps_paragraph_format(test_font: Path) -> None:
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    paragraph = SourceParagraph(
        (SourceTextRun("word " * 120),),
        first_line_indent_mm=10,
        semantic_role="body",
    )
    element = SourceTextElement(
        "paragraph", 0, 0, (paragraph.text,), styled_paragraphs=(paragraph,)
    )
    document = SourceDocument(
        Path("page-break.docx"), (SourcePage(0, None, None, (element,)),)
    )
    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("small", 80, 55),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            paragraph_options=config["paragraphs"],
            preserve_source_page_breaks=False,
        )

    assert len(result.pages) > 1
    assert min(glyph.x_mm for glyph in result.pages[0].layout.glyphs) == 10
    assert min(glyph.x_mm for glyph in result.pages[1].layout.glyphs) == 10
    assert result.element_details["paragraph"]["paragraphs"][0]["line_count"] > 1
