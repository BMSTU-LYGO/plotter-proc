from pathlib import Path

from plotter_processor.document_models import SourceParagraph, SourceTextRun
from tests.test_paragraph_layout import _layout


def _word_left(result, word_index: int) -> float:
    return min(glyph.x_mm for glyph in result.lines[0].glyphs if glyph.word_index == word_index)


def test_custom_tab_stop_is_used(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("Key\tValue"),),
        left_indent_mm=5,
        tab_stops_mm=(30,),
        semantic_role="body",
    )
    result = _layout(paragraph, test_font)

    assert abs(_word_left(result, 1) - 45) < 0.01


def test_default_tab_stops_start_at_paragraph_left(test_font: Path) -> None:
    paragraph = SourceParagraph(
        (SourceTextRun("Key\tValue"),), left_indent_mm=5, semantic_role="body"
    )
    result = _layout(paragraph, test_font)

    assert abs(_word_left(result, 1) - 27.5) < 0.01
