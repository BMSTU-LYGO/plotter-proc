from pathlib import Path

from plotter_processor.document_models import (
    SourceDocument,
    SourceMathElement,
    SourceTableElement,
    SourceTextElement,
)
from plotter_processor.models import DocumentText
from plotter_processor.structured_document_reader import (
    read_structured_document,
)

PDF_TEXT_LAYER_ERROR = (
    "PDF does not contain a usable text layer. OCR is not supported in MVP."
)


def read_document(source_path: str | Path) -> DocumentText:
    path = Path(source_path)
    document = read_structured_document(path)
    paragraphs = _textual_projection(document)
    text = "\n".join(paragraphs)
    if path.suffix.lower() == ".pdf" and len("".join(text.split())) < 10:
        raise ValueError(PDF_TEXT_LAYER_ERROR)
    return DocumentText(paragraphs, path, list(document.warnings))


def _textual_projection(document: SourceDocument) -> list[str]:
    paragraphs: list[str] = []
    for page in document.pages:
        for element in sorted(page.elements, key=lambda item: item.source_order):
            if isinstance(element, SourceTextElement):
                paragraphs.extend(element.paragraphs)
            elif isinstance(element, SourceTableElement):
                for cell in sorted(element.cells, key=lambda item: (item.row, item.column)):
                    paragraphs.extend(paragraph.text for paragraph in cell.paragraphs)
            elif isinstance(element, SourceMathElement):
                paragraphs.append(element.expression)
    return paragraphs
