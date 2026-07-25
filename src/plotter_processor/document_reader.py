from pathlib import Path

import pymupdf
from docx import Document

from plotter_processor.models import DocumentText

SUPPORTED_EXTENSIONS = {".docx", ".pdf"}
PDF_TEXT_LAYER_ERROR = (
    "PDF does not contain a usable text layer. OCR is not supported in MVP."
)


def read_document(source_path: str | Path) -> DocumentText:
    path = Path(source_path)
    extension = path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported input format '{extension or '(none)'}'. Use {supported}.")
    if not path.is_file():
        raise FileNotFoundError(f"Input document does not exist: {path}")

    if extension == ".docx":
        return _read_docx(path)
    return _read_pdf(path)


def _read_docx(path: Path) -> DocumentText:
    try:
        document = Document(path)
    except Exception as error:
        raise ValueError(f"Cannot read DOCX document: {path}") from error

    return DocumentText(
        paragraphs=[paragraph.text for paragraph in document.paragraphs],
        source_path=path,
        warnings=[],
    )


def _read_pdf(path: Path) -> DocumentText:
    try:
        document = pymupdf.open(path)
    except Exception as error:
        raise ValueError(f"Cannot read PDF document: {path}") from error

    pages: list[str] = []
    try:
        for page in document:
            blocks = page.get_text("blocks", sort=True)
            text_blocks = [block for block in blocks if len(block) < 7 or block[6] == 0]
            text_blocks.sort(key=lambda block: (round(block[1], 3), round(block[0], 3)))
            page_text = "\n".join(
                str(block[4]).strip("\n") for block in text_blocks if str(block[4]).strip()
            )
            pages.append(page_text)
    finally:
        document.close()

    text = "\n\n".join(pages)
    if len("".join(text.split())) < 10:
        raise ValueError(PDF_TEXT_LAYER_ERROR)

    return DocumentText(
        paragraphs=text.split("\n"),
        source_path=path,
        warnings=[],
    )
