"""Small, dependency-free Markdown reader for the common document model.

Markdown is intentionally treated as text input.  This module never renders
HTML, evaluates embedded content, or retrieves linked resources.
"""

from __future__ import annotations

import html
from pathlib import Path
import re

from plotter_processor.document_models import (
    DocumentMetadata,
    DocumentModel,
    SourcePage,
    SourceParagraph,
    SourceTextElement,
    SourceTextRun,
)


SUPPORTED_EXTENSIONS = {".md", ".markdown"}

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+[ \t]*)?$")
_LIST_RE = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])[ \t]+(.*)$")
_QUOTE_RE = re.compile(r"^ {0,3}>[ \t]?(.*)$")
_IMAGE_RE = re.compile(r"!\[([^]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"(?<!!)\[([^]]*)\]\([^)]*\)")
_REFERENCE_LINK_RE = re.compile(r"(?<!!)\[([^]]*)\]\[[^]]*\]")
_INLINE_CODE_RE = re.compile(r"(`+)(.*?)\1")
_STRONG_OR_EMPHASIS_RE = re.compile(r"(?<!\\)(\*\*|__|\*|_)(.+?)(?<!\\)\1")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def read_markdown_document(source_path: str | Path) -> DocumentModel:
    """Read a local UTF-8 Markdown file into one textual source page.

    Every source line becomes a paragraph, including blank lines.  Block
    markers are removed while their content remains readable; code-fence
    contents are preserved verbatim.
    """

    path = Path(source_path)
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported Markdown format '{extension or '(none)'}'. Use {supported}.")
    if not path.is_file():
        raise FileNotFoundError(f"Input document does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise ValueError(f"Markdown document is not valid UTF-8: {path}") from error
    except OSError as error:
        raise ValueError(f"Cannot read Markdown document: {path}") from error
    if not text.strip():
        raise ValueError(f"Markdown document contains no usable text: {path}")

    paragraphs, roles = _markdown_paragraphs(text)
    styled = tuple(
        SourceParagraph((SourceTextRun(paragraph),), semantic_role=role)
        for paragraph, role in zip(paragraphs, roles, strict=True)
    )
    element = SourceTextElement(
        "page-001-text-001", 0, 0, paragraphs, styled_paragraphs=styled
    )
    return DocumentModel(
        path,
        (SourcePage(0, None, None, (element,)),),
        metadata=DocumentMetadata(source_format="markdown"),
    )


def _markdown_paragraphs(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    paragraphs: list[str] = []
    roles: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence is not None:
            if fence_match and fence_match.group(1)[0] == fence[0] and len(fence_match.group(1)) >= len(fence):
                fence = None
                continue
            paragraphs.append(line)
            roles.append("code")
            continue
        if fence_match:
            fence = fence_match.group(1)
            continue

        role = "body"
        heading = _HEADING_RE.match(line)
        if heading:
            line = heading.group(1)
            role = "heading"
        else:
            quote = _QUOTE_RE.match(line)
            if quote:
                line = quote.group(1)
                role = "blockquote"
            listing = _LIST_RE.match(line)
            if listing:
                line = listing.group(1)
                role = "list"
        paragraphs.append(_clean_inline_markdown(line))
        roles.append(role)
    return tuple(paragraphs), tuple(roles)


def _clean_inline_markdown(text: str) -> str:
    """Retain readable inline text without interpreting markup or HTML."""

    text = _HTML_COMMENT_RE.sub("", text)
    text = _IMAGE_RE.sub(lambda match: match.group(1), text)
    text = _LINK_RE.sub(lambda match: match.group(1), text)
    text = _REFERENCE_LINK_RE.sub(lambda match: match.group(1), text)
    text = _INLINE_CODE_RE.sub(lambda match: match.group(2), text)
    # Repeat so nested emphasis such as **an *important* note** is unwrapped.
    previous = None
    while text != previous:
        previous = text
        text = _STRONG_OR_EMPHASIS_RE.sub(lambda match: match.group(2), text)
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text).replace("\\*", "*").replace("\\_", "_").replace("\\`", "`")
