from pathlib import Path

import pytest

from plotter_processor.document_models import DocumentModel, SourceTextElement
from plotter_processor.markdown_document_reader import read_markdown_document


def test_markdown_preserves_lines_and_turns_blocks_into_text(tmp_path: Path) -> None:
    source = tmp_path / "input.md"
    source.write_text(
        "# A title\n\n- first **item**\n2. `second` item\n> quoted *text*\n",
        encoding="utf-8",
    )

    document = read_markdown_document(source)

    assert isinstance(document, DocumentModel)
    assert document.metadata.source_format == "markdown"
    element = document.pages[0].elements[0]
    assert isinstance(element, SourceTextElement)
    assert element.paragraphs == ("A title", "", "first item", "second item", "quoted text")
    assert [paragraph.semantic_role for paragraph in element.styled_paragraphs] == [
        "heading", "body", "list", "list", "blockquote",
    ]


def test_markdown_keeps_fenced_code_verbatim_and_never_resolves_resources(tmp_path: Path) -> None:
    source = tmp_path / "example.markdown"
    source.write_text(
        "Before [website](https://example.invalid) and ![diagram](https://example.invalid/a.png)\n"
        "```python\nprint('`not markup`')\n```\n"
        "After <script>alert(1)</script>\n",
        encoding="utf-8",
    )

    document = read_markdown_document(source)

    element = document.pages[0].elements[0]
    assert isinstance(element, SourceTextElement)
    assert element.paragraphs == (
        "Before website and diagram",
        "print('`not markup`')",
        "After alert(1)",
    )
    assert [paragraph.semantic_role for paragraph in element.styled_paragraphs] == ["body", "code", "body"]


def test_markdown_rejects_other_extensions(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported Markdown format"):
        read_markdown_document(source)
