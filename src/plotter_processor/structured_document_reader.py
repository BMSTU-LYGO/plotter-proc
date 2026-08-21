from __future__ import annotations

from pathlib import Path

from plotter_processor.document_models import (
    SourceDocument,
    SourcePage,
    SourceParagraph,
    SourceTextElement,
    SourceTextRun,
)

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".txt"}


def read_structured_document(
    source_path: str | Path,
    *,
    assets_dir: str | Path | None = None,
    pdf_math_mode: str = "off",
    pdf_math_options: dict[str, object] | None = None,
    math_debug_dir: str | Path | None = None,
) -> SourceDocument:
    path = Path(source_path)
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported input format '{extension or '(none)'}'. Use {supported}.")
    if not path.is_file():
        raise FileNotFoundError(f"Input document does not exist: {path}")
    asset_root = Path(assets_dir) if assets_dir is not None else path.parent / ".extracted-assets"
    if extension == ".pdf":
        from plotter_processor.pdf_document_reader import read_pdf_document

        return read_pdf_document(
            path,
            asset_root,
            math_mode=pdf_math_mode,
            math_options=pdf_math_options,
            math_debug_dir=Path(math_debug_dir) if math_debug_dir is not None else None,
        )
    if extension == ".docx":
        from plotter_processor.docx_document_reader import read_docx_document

        return read_docx_document(path, asset_root)
    return _read_txt(path)


def _read_txt(path: Path) -> SourceDocument:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise ValueError(f"TXT document is not valid UTF-8: {path}") from error
    except OSError as error:
        raise ValueError(f"Cannot read TXT document: {path}") from error
    if not text.strip():
        raise ValueError(f"TXT document contains no usable text: {path}")
    paragraphs = tuple(text.splitlines())
    styled = tuple(
        SourceParagraph((SourceTextRun(paragraph),), semantic_role="body")
        for paragraph in paragraphs
    )
    element = SourceTextElement(
        "page-001-text-001", 0, 0, paragraphs, styled_paragraphs=styled
    )
    return SourceDocument(path, (SourcePage(0, None, None, (element,)),))
