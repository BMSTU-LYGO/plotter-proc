from plotter_processor.handwriting import JoiningConfig, route_words
from plotter_processor.models import PathDocument, PlotterStroke, Point, PositionedGlyph


def _glyph(char: str, index: int, x: float, word: int) -> PositionedGlyph:
    return PositionedGlyph(char, ord(char), char, x, 10, 2, 0.01, 0, index, word_index=word)


def test_connections_never_cross_word_boundary() -> None:
    glyphs = [_glyph("а", 0, 0, 0), _glyph("б", 1, 2, 1)]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а"),
            PlotterStroke(1, [Point(2.2, 10), Point(4, 10)], False, 1, "б"),
        ],
        [],
    )
    config = JoiningConfig(True, 2, 55, 0.2, frozenset(), frozenset(), True)
    result, metrics = route_words(document, glyphs, config)
    assert len(result.strokes) == 2
    assert metrics["connected_pairs"] == 0


def test_punctuation_is_rejected_with_no_false_line() -> None:
    glyphs = [_glyph("а", 0, 0, 0), _glyph(",", 1, 2, 0)]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а"),
            PlotterStroke(1, [Point(2.2, 10), Point(3, 10)], False, 1, ","),
        ],
        [],
    )
    config = JoiningConfig(True, 2, 55, 0.2, frozenset(","), frozenset(), True)
    result, metrics = route_words(document, glyphs, config)
    assert len(result.strokes) == 2
    assert metrics["rejections_by_reason"]["punctuation_rule"] == 1
