from pathlib import Path

import pytest
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
from plotter_processor.page_grid import resolve_page_grid
from plotter_processor.paragraph_layout import layout_paragraph


def _config() -> dict[str, object]:
    return yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))


def test_disabled_grid_preserves_existing_configuration() -> None:
    assert not resolve_page_grid({"enabled": False}).enabled


def test_grid_rejects_non_positive_cell_size() -> None:
    with pytest.raises(ValueError, match="cell_width_mm must be positive"):
        resolve_page_grid({
            "enabled": True,
            "cell_width_mm": 0,
            "cell_height_mm": 5,
            "origin_x_mm": 0,
            "origin_y_mm": 0,
            "baseline_offset_mm": 0,
        })


def test_text_baselines_use_absolute_grid_lines(test_font: Path) -> None:
    config = _config()
    paragraph = SourceParagraph((SourceTextRun("word " * 40),), semantic_role="body")
    element = SourceTextElement(
        "grid-text", 0, 0, (paragraph.text,), styled_paragraphs=(paragraph,)
    )
    document = SourceDocument(Path("grid.txt"), (SourcePage(0, None, None, (element,)),))
    grid = {
        "enabled": True,
        "cell_width_mm": 5.0,
        "cell_height_mm": 5.0,
        "origin_x_mm": 1.0,
        "origin_y_mm": 2.0,
        "baseline_offset_mm": 0.5,
    }
    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("A5", 148, 210),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            paragraph_options=config["paragraphs"],
            grid_options=grid,
        )

    baselines = sorted({glyph.baseline_y_mm for glyph in result.pages[0].layout.glyphs})
    assert len(baselines) > 2
    assert all((baseline - 2.5) / 5 == pytest.approx(round((baseline - 2.5) / 5)) for baseline in baselines)


def test_cell_indents_and_tabs_are_converted_without_changing_glyph_size(
    test_font: Path,
) -> None:
    config = _config()
    paragraph = SourceParagraph((SourceTextRun("first\tsecond " * 8),))
    options = dict(config["paragraphs"])
    options.update({
        "grid_cell_width_mm": 5.0,
        "indent_cells": 2,
        "first_line_indent_cells": 1,
        "tab_interval_cells": 3,
    })
    with load_font(test_font) as font:
        result = layout_paragraph(
            paragraph,
            font,
            content_left_mm=10,
            content_right_mm=130,
            base_size_options=config["sizes"]["normal"],
            paragraph_options=options,
        )

    assert result.lines[0].left_mm == 25
    assert result.lines[1].left_mm == 20
    assert result.tab_stops_mm == ()
    assert result.lines[0].advance_mm > 0
