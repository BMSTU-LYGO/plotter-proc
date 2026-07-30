from pathlib import Path

from plotter_processor.models import DocumentText
from plotter_processor.text_normalizer import normalize_document, normalize_text


def test_preserves_yo_and_nonbreaking_space() -> None:
    text, warnings = normalize_text("Ёжик\tест  ещё\u00a0ел")

    assert text == "Ёжик ест ещё\u00a0ел"
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


def test_preserves_printable_unicode() -> None:
    text, warnings = normalize_text("Цена © 10")

    assert text == "Цена © 10"
    assert warnings == []


def test_warns_once_for_each_control_character() -> None:
    text, warnings = normalize_text("a\x00а\x00a")

    assert text == "a а a"
    assert warnings == ["Control character U+0000 was replaced with a space"]


def test_keeps_supported_punctuation() -> None:
    source = """Тест: №1 — (да); [нет]? 10% + 2 = 12 / 3 \\ 4, «ок»!"""

    text, warnings = normalize_text(source)

    assert text == source
    assert warnings == []
