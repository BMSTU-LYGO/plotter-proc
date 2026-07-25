from pathlib import Path

import pymupdf
import pytest
from docx import Document

from plotter_processor.document_reader import PDF_TEXT_LAYER_ERROR, read_document


def test_reads_docx_paragraphs_and_preserves_empty_paragraphs(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    document = Document()
    document.add_paragraph("Первый абзац")
    document.add_paragraph("")
    document.add_paragraph("Second paragraph")
    document.save(source)

    result = read_document(source)

    assert result.paragraphs == ["Первый абзац", "", "Second paragraph"]
    assert result.source_path == source
    assert result.warnings == []


def test_docx_tables_are_not_extracted(tmp_path: Path) -> None:
    source = tmp_path / "table.docx"
    document = Document()
    document.add_paragraph("Visible paragraph")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Ignored table text"
    document.save(source)

    result = read_document(source)

    assert result.paragraphs == ["Visible paragraph"]


def test_reads_pdf_text_layer_in_page_order(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    document = pymupdf.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "First page text")
    second_page = document.new_page()
    second_page.insert_text((72, 72), "Second page text")
    document.save(source)
    document.close()

    result = read_document(source)

    extracted = "\n".join(result.paragraphs)
    assert "First page text" in extracted
    assert "Second page text" in extracted
    assert extracted.index("First page text") < extracted.index("Second page text")


def test_rejects_pdf_without_usable_text_layer(tmp_path: Path) -> None:
    source = tmp_path / "empty.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(source)
    document.close()

    with pytest.raises(ValueError, match="OCR is not supported"):
        read_document(source)

    assert PDF_TEXT_LAYER_ERROR.endswith("MVP.")


def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("plain text", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported input format"):
        read_document(source)
