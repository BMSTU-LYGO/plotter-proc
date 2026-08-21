from pathlib import Path

import pytest
import yaml

from plotter_processor.document_models import (
    SourceParagraph,
    SourceTableCell,
    SourceTableElement,
    SourceTextRun,
)
from plotter_processor.font_loader import load_font
from plotter_processor.table_layout import layout_table_fragment, plan_table_layout


def _table(widths=(30.0, 60.0, 30.0)) -> SourceTableElement:
    cells = tuple(
        SourceTableCell(0, column, 1, 1, (SourceParagraph((SourceTextRun("cell"),)),))
        for column in range(3)
    )
    return SourceTableElement("table", 0, 0, 1, 3, cells, widths)


def _options():
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    return config["sizes"]["normal"], config["paragraphs"], config["tables"]


def test_column_ratios_small_table_and_wide_table(test_font: Path) -> None:
    sizes, paragraphs, tables = _options()
    with load_font(test_font) as font:
        small = plan_table_layout(
            _table((10, 20, 10)), font, available_width_mm=128, page_scale=0.68,
            size_options=sizes, paragraph_options=paragraphs, table_options=tables,
        )
        wide = plan_table_layout(
            _table(), font, available_width_mm=60, page_scale=1.0,
            size_options=sizes, paragraph_options=paragraphs, table_options=tables,
        )

    assert small.width_mm == pytest.approx(27.2)
    assert small.column_widths_mm[1] / small.column_widths_mm[0] == pytest.approx(2)
    assert small.width_mm < 128
    assert wide.width_mm == pytest.approx(60)
    assert wide.column_widths_mm[1] / wide.column_widths_mm[0] == pytest.approx(2)


def test_horizontal_merge_has_no_internal_vertical_border(test_font: Path) -> None:
    sizes, paragraphs, tables = _options()
    merged = SourceTableElement(
        "merged", 0, 0, 1, 3,
        (
            SourceTableCell(0, 0, 1, 1, (SourceParagraph((SourceTextRun("a"),)),)),
            SourceTableCell(0, 1, 1, 2, (SourceParagraph((SourceTextRun("merged"),)),)),
        ),
        (30, 30, 30),
    )
    with load_font(test_font) as font:
        plan = plan_table_layout(
            merged, font, available_width_mm=90, page_scale=1,
            size_options=sizes, paragraph_options=paragraphs, table_options=tables,
        )
        fragment = layout_table_fragment(
            merged, [0], font, x=0, y=0, size_options=sizes, plan=plan
        )

    assert not any(
        stroke.points[0].x == 60
        and stroke.points[1].x == 60
        and stroke.points[0].y != stroke.points[1].y
        for stroke in fragment.strokes
    )
