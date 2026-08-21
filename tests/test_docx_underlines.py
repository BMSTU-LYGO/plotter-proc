from pathlib import Path

from plotter_processor.document_models import SourceTextElement
from plotter_processor.structured_document_reader import read_structured_document


def test_docx_single_double_and_words_underlines_are_imported(tmp_path: Path) -> None:
    document = read_structured_document(Path("tests/fixtures/update_7/lines_tables/underline_runs.docx"), assets_dir=tmp_path)
    styles = [run.style.underline for element in document.elements if isinstance(element, SourceTextElement) for paragraph in element.styled_paragraphs for run in paragraph.runs]
    assert styles == ["single", None, "double", "words"]
