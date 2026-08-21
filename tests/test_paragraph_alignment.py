from pathlib import Path

from plotter_processor.document_models import SourceParagraph, SourceTextRun
from tests.test_paragraph_layout import _layout


def test_center_uses_indented_paragraph_width(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("center"),),
        alignment="center",
        left_indent_mm=10,
        right_indent_mm=5,
        semantic_role="body",
    )
    line = _layout(paragraph, test_font).lines[0]

    assert abs((line.used_left_mm + line.used_right_mm) / 2 - (20 + 65) / 2) < 0.01


def test_right_uses_right_indent(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("right"),),
        alignment="right",
        right_indent_mm=8,
        semantic_role="body",
    )
    line = _layout(paragraph, test_font).lines[0]

    assert abs(line.used_right_mm - 62) < 0.01


def test_justify_skips_last_line_and_stretches_only_word_gaps(test_font: Path) -> None:
    text = "one two three four five six seven eight nine ten"
    left = _layout(SourceParagraph((SourceTextRun(text),), semantic_role="body"), test_font, right=42)
    justified = _layout(
        SourceParagraph((SourceTextRun(text),), alignment="justify", semantic_role="body"),
        test_font,
        right=42,
    )

    assert len(justified.lines) > 1
    assert justified.lines[0].used_right_mm > left.lines[0].used_right_mm
    assert justified.lines[-1].used_left_mm == left.lines[-1].used_left_mm
    first_word = [glyph for glyph in justified.lines[0].glyphs if glyph.word_index == 0]
    assert [glyph.x_mm for glyph in first_word] == [
        glyph.x_mm for glyph in left.lines[0].glyphs if glyph.word_index == 0
    ]
