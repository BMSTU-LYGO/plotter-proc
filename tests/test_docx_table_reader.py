from pathlib import Path

from plotter_processor.document_models import SourceTableElement
from plotter_processor.structured_document_reader import read_structured_document


def test_simple_docx_table_is_structured(tmp_path: Path) -> None:
    document = read_structured_document(Path("tests/fixtures/update_7/lines_tables/simple_table.docx"), assets_dir=tmp_path)
    table = next(item for item in document.elements if isinstance(item, SourceTableElement))
    assert (table.rows, table.columns, len(table.cells)) == (3, 3, 9)
    assert "docx_table_layout_simplified" not in document.warnings


def test_docx_merged_cells_keep_spans(tmp_path: Path) -> None:
    document = read_structured_document(Path("tests/fixtures/update_7/lines_tables/merged_cells.docx"), assets_dir=tmp_path)
    table = next(item for item in document.elements if isinstance(item, SourceTableElement))
    assert any(cell.column_span == 2 for cell in table.cells)
    assert any(cell.row_span == 2 for cell in table.cells)
