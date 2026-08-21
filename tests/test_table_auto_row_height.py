from pathlib import Path

import yaml

from plotter_processor.document_models import (
    SourceParagraph,
    SourceTableCell,
    SourceTableElement,
    SourceTextRun,
)
from plotter_processor.font_loader import load_font
from plotter_processor.table_layout import layout_table_fragment, plan_table_layout


def _config():
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    return config["sizes"]["normal"], config["paragraphs"], config["tables"]


def test_wrapping_increases_row_height_and_text_stays_inside(test_font: Path) -> None:
    sizes, paragraphs, tables = _config()
    cell = SourceTableCell(
        0, 0, 1, 1,
        (SourceParagraph((SourceTextRun("long cell text " * 18),), first_line_indent_mm=3),),
    )
    table = SourceTableElement("table", 0, 0, 1, 1, (cell,), (35,))
    with load_font(test_font) as font:
        plan = plan_table_layout(
            table, font, available_width_mm=35, page_scale=1,
            size_options=sizes, paragraph_options=paragraphs, table_options=tables,
        )
        fragment = layout_table_fragment(table, [0], font, x=5, y=7, size_options=sizes, plan=plan)

    assert plan.row_heights_mm[0] > 8
    assert plan.auto_height_rows == 1
    assert max(glyph.x_mm + glyph.advance_mm for glyph in fragment.glyphs) < 40
    assert max(glyph.baseline_y_mm for glyph in fragment.glyphs) < 7 + fragment.height_mm


def test_bottom_vertical_alignment_moves_short_text_down(test_font: Path) -> None:
    sizes, paragraphs, tables = _config()
    top = SourceTableCell(0, 0, 1, 1, (SourceParagraph((SourceTextRun("top"),)),), vertical_alignment="top")
    bottom = SourceTableCell(0, 1, 1, 1, (SourceParagraph((SourceTextRun("bottom"),)),), vertical_alignment="bottom")
    table = SourceTableElement("table", 0, 0, 1, 2, (top, bottom), (35, 35), row_heights_mm=(30,))
    with load_font(test_font) as font:
        plan = plan_table_layout(
            table, font, available_width_mm=70, page_scale=1,
            size_options=sizes, paragraph_options=paragraphs, table_options=tables,
        )
        fragment = layout_table_fragment(table, [0], font, x=0, y=0, size_options=sizes, plan=plan)

    top_baseline = min(g.baseline_y_mm for g in fragment.glyphs if g.word_index == 0)
    bottom_baseline = min(g.baseline_y_mm for g in fragment.glyphs if g.word_index == 1)
    assert bottom_baseline > top_baseline

