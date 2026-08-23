from pathlib import Path

import pytest
import yaml

from plotter_processor.document_models import (
    SourceDocument,
    SourcePage,
    SourceParagraph,
    SourceTableCell,
    SourceTableElement,
    SourceTextRun,
)
from plotter_processor.document_paginator import paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec


def test_headers_repeat_rows_stay_whole_and_row_span_is_protected(test_font: Path) -> None:
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    cells = [
        SourceTableCell(row, column, 1, 1, (SourceParagraph((SourceTextRun(f"R{row} C{column} " * 3),)),))
        for row in range(10) for column in range(2)
    ]
    cells = [cell for cell in cells if not (cell.row == 5 and cell.column == 0)]
    cells.append(SourceTableCell(4, 0, 2, 1, (SourceParagraph((SourceTextRun("merged rows 4 5"),)),)))
    table = SourceTableElement(
        "table", 0, 0, 10, 2, tuple(cells), (35, 55), repeat_header_rows=1
    )
    document = SourceDocument(Path("table.docx"), (SourcePage(0, 100, 140, (table,)),))
    with load_font(test_font) as font:
        result = paginate_document(
            document, font, PageSpec("small", 100, 75), config["margins_mm"],
            config["sizes"]["normal"], config["images"], config["pagination"],
            paragraph_options=config["paragraphs"], table_options=config["tables"],
            preserve_source_page_breaks=False,
        )

    fragments = [fragment for page in result.pages for fragment in page.metadata["table_fragments"]]
    assert len(fragments) > 1
    assert all(fragment["rows"][0] == 0 for fragment in fragments[1:])
    assert all(not ((4 in fragment["rows"]) ^ (5 in fragment["rows"])) for fragment in fragments)
    assert all(
        fragment["target_bbox"]["height"]
        == pytest.approx(sum(fragment["row_heights_mm"]), abs=1e-6)
        for fragment in fragments
    )
    assert result.import_statistics["table_splits"] == len(fragments) - 1
    assert result.import_statistics["repeated_headers_emitted"] == len(fragments) - 1
    assert result.import_statistics["shared_borders_suppressed"] > 0
