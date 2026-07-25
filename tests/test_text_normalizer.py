from pathlib import Path

from plotter_processor.models import DocumentText
from plotter_processor.text_normalizer import normalize_document, normalize_text


def test_replaces_yo_and_normalizes_whitespace() -> None:
    text, warnings = normalize_text("Ёжик\tест  ещё\u00a0ел")

    assert text == "Ежик ест еще ел"
    assert warnings == []


def test_normalizes_line_endings_and_limits_empty_lines() -> None:
    text, _ = normalize_text("Один\r\n\r\n\r\n\r\nДва\rТри")

    assert text == "Один\n\n\nДва\nТри"


def test_preserves_paragraphs() -> None:
    document = DocumentText(
        paragraphs=["Первый", "", "Второй"],
        source_path=Path("input.docx"),
        warnings=[],
    )

    result = normalize_document(document)

    assert result.paragraphs == ["Первый", "", "Второй"]


def test_replaces_unsupported_character_and_adds_warning() -> None:
    text, warnings = normalize_text("Цена © 10")

    assert text == "Цена 10"
    assert warnings == ["Character '©' was replaced with a space"]


def test_warns_once_for_each_unsupported_character() -> None:
    text, warnings = normalize_text("aаa")

    assert text == " а "
    assert warnings == ["Character 'a' was replaced with a space"]


def test_keeps_supported_punctuation() -> None:
    source = """Тест: №1 — (да); [нет]? 10% + 2 = 12 / 3 \\ 4, «ок»!"""

    text, warnings = normalize_text(source)

    assert text == source
    assert warnings == []
