from pathlib import Path

import pytest

from plotter_processor.document_models import SourceTableElement
from plotter_processor.pipeline import _paragraph_formatting_report
from plotter_processor.structured_document_reader import read_structured_document


def test_docx_table_properties_row_heights_and_vertical_alignment(tmp_path: Path) -> None:
    document = read_structured_document(
        Path("tests/fixtures/layout/a4_to_a5_layout_demo.docx"), assets_dir=tmp_path / "assets"
    )
    table = next(item for item in document.elements if isinstance(item, SourceTableElement))

    assert table.alignment == "center"
    assert table.column_widths_mm[1] / table.column_widths_mm[0] == pytest.approx(
        3, abs=0.002
    )
    assert table.repeat_header_rows == 1
    assert table.row_heights_mm[5] and table.row_heights_mm[5] > 12
    assert any(cell.column_span == 2 for cell in table.cells)
    assert any(cell.row_span == 2 for cell in table.cells)
    assert any(cell.vertical_alignment == "bottom" for cell in table.cells)


def test_full_demo_exposes_paragraph_formatting_metrics(tmp_path: Path) -> None:
    document = read_structured_document(
        Path("tests/fixtures/layout/upd10_full_demo.docx"),
        assets_dir=tmp_path / "full-assets",
    )
    metrics = _paragraph_formatting_report(document)

    assert metrics["paragraphs_total"] > 0
    assert metrics["titles"] == 1
    assert metrics["headings"] >= 1
    assert metrics["first_line_indents"] >= 1
    assert metrics["centered"] >= 1
    assert metrics["right_aligned"] >= 1
    assert metrics["justified"] >= 1
    assert metrics["custom_tab_stops"] >= 1
