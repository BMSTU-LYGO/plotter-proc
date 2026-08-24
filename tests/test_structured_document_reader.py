from pathlib import Path

from plotter_processor.document_models import DocumentModel, SourceTextElement
from plotter_processor.structured_document_reader import read_structured_document


def test_txt_has_structured_page_and_text_element(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("one\ntwo", encoding="utf-8")

    document = read_structured_document(source)

    assert isinstance(document, DocumentModel)
    assert document.metadata.source_format == "txt"
    assert len(document.pages) == 1
    assert isinstance(document.pages[0].elements[0], SourceTextElement)
    assert document.pages[0].elements[0].paragraphs == ("one", "two")
