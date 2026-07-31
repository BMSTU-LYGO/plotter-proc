from pathlib import Path

from plotter_processor.handwriting import (
    JoiningConfig,
    VariationConfig,
    apply_variation,
    export_handwriting_debug,
    route_words,
)
from plotter_processor.models import PathDocument, PlotterStroke, Point, PositionedGlyph


def _glyph(char: str, index: int, x: float, *, line: int = 0) -> PositionedGlyph:
    return PositionedGlyph(char, ord(char), char, x, 10, 2, 0.01, line, index)


def _config() -> JoiningConfig:
    return JoiningConfig(True, 2, 80, 0.2, frozenset(".,!?:;)"), frozenset("(«-"), True)


def test_joins_letters_inside_word_and_preserves_word_gap() -> None:
    glyphs = [_glyph("а", 0, 0), _glyph("б", 1, 2), _glyph("в", 2, 6)]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(2.5, 10), Point(4, 10)], False, 1, "б", 0),
            PlotterStroke(2, [Point(6, 10), Point(8, 10)], False, 2, "в", 0),
        ],
        [],
    )
    result, metrics = route_words(document, glyphs, _config())
    assert len(result.strokes) == 2
    assert metrics["joins_created"] == 1
    assert metrics["pen_lifts_saved_between_glyphs"] == 1


def test_diacritic_remains_a_separate_stroke() -> None:
    glyphs = [_glyph("ё", 0, 0), _glyph("ж", 1, 2)]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "ё", 0),
            PlotterStroke(1, [Point(1, 8), Point(1.1, 8)], False, 0, "ё", 1),
            PlotterStroke(2, [Point(2.5, 10), Point(4, 10)], False, 1, "ж", 0),
        ],
        [],
    )
    result, metrics = route_words(document, glyphs, _config())
    assert metrics["joins_created"] == 1
    assert len(result.strokes) == 2
    assert any(stroke.contour_index == 1 for stroke in result.strokes)


def test_disabled_joining_returns_original_document() -> None:
    document = PathDocument(
        10, 10, [PlotterStroke(0, [Point(0, 0), Point(1, 0)], False, 0, "а", 0)], []
    )
    config = JoiningConfig(False, 2, 80, 0.2, frozenset(), frozenset(), True)
    result, metrics = route_words(document, [_glyph("а", 0, 0)], config)
    assert result is document
    assert metrics["enabled"] is False


def test_variation_seed_is_deterministic_and_debug_has_layers(tmp_path: Path) -> None:
    document = PathDocument(
        10, 10, [PlotterStroke(0, [Point(1, 5), Point(2, 5)], False, 0, "а", 0)], []
    )
    config = VariationConfig(True, 7, 0.1, 1, 2, 0.1)
    glyphs = [_glyph("а", 0, 1)]
    first = apply_variation(document, glyphs, config)
    second = apply_variation(document, glyphs, config)
    assert first.strokes[0].points == second.strokes[0].points
    output = tmp_path / "debug.svg"
    export_handwriting_debug(first, output)
    svg = output.read_text(encoding="utf-8")
    assert 'id="strokes"' in svg
    assert 'id="entry-exit"' in svg
    assert 'id="travel"' in svg
