from dataclasses import replace
from pathlib import Path

from plotter_processor import handwriting
from plotter_processor.handwriting import (
    JoiningConfig,
    VariationConfig,
    _SegmentObstacleIndex,
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


def test_variation_reuses_one_transform_for_all_glyph_strokes(monkeypatch) -> None:
    document = PathDocument(
        10,
        10,
        [
            PlotterStroke(0, [Point(1, 5), Point(2, 5)], False, 0, "а", 0),
            PlotterStroke(1, [Point(1, 4), Point(2, 4)], False, 0, "а", 1),
        ],
        [],
    )
    config = VariationConfig(True, 7, 0.1, 1, 2, 0.1)
    calls = {"cos": 0, "sin": 0}
    original_cos = handwriting.math.cos
    original_sin = handwriting.math.sin

    def counted_cos(value: float) -> float:
        calls["cos"] += 1
        return original_cos(value)

    def counted_sin(value: float) -> float:
        calls["sin"] += 1
        return original_sin(value)

    monkeypatch.setattr(handwriting.math, "cos", counted_cos)
    monkeypatch.setattr(handwriting.math, "sin", counted_sin)

    result = apply_variation(document, [_glyph("а", 0, 1)], config)

    assert len(result.strokes) == 2
    assert calls == {"cos": 1, "sin": 1}


def test_segment_index_returns_overlapping_segments_in_source_order() -> None:
    strokes = [
        PlotterStroke(0, [Point(0, 0), Point(1, 1)], False),
        PlotterStroke(1, [Point(50, 50), Point(51, 51)], False),
        PlotterStroke(2, [Point(2, 0), Point(3, 1)], False),
    ]
    index = _SegmentObstacleIndex.build(strokes, cell_size_mm=4)

    assert [item.stroke.id for item in index.query((-1, -1, 4, 2))] == [0, 2]
    assert index.query((10, 10, 11, 11)) == []


def test_distance_rejections_skip_bezier_and_collision_work() -> None:
    glyphs = [
        replace(_glyph("а", index, index * 10.0), word_index=0)
        for index in range(1001)
    ]
    document = PathDocument(
        10020,
        20,
        [
            PlotterStroke(
                index,
                [Point(index * 10.0, 10), Point(index * 10.0 + 1, 10)],
                False,
                index,
                "а",
                0,
            )
            for index in range(1001)
        ],
        [],
    )

    result, metrics = route_words(document, glyphs, _config())

    assert len(result.strokes) == 1001
    assert metrics["cheap_rejected_pairs"] == 1000
    assert metrics["beziers_built"] == 0
    assert metrics["collision_queries"] == 0
    assert metrics["segments_tested"] == 0
    assert "connection_debug" not in result.metadata


def test_aggressive_accepts_bounded_gap_that_safe_rejects() -> None:
    glyphs = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 4.5), word_index=0),
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(4.5, 10), Point(6, 10)], False, 1, "б", 0),
        ],
        [],
    )
    safe = _config()
    aggressive = replace(
        safe,
        max_join_gap_mm=3,
        max_join_angle_deg=85,
        max_vertical_offset_mm=1.8,
        mode="aggressive",
    )

    safe_result, safe_metrics = route_words(document, glyphs, safe)
    aggressive_result, aggressive_metrics = route_words(document, glyphs, aggressive)

    assert len(safe_result.strokes) == 2
    assert safe_metrics["rejections_by_reason"] == {"distance": 1}
    assert len(aggressive_result.strokes) == 1
    assert aggressive_metrics["joins_created"] == 1


def test_aggressive_keeps_collision_and_punctuation_guards() -> None:
    safe = _config()
    aggressive = replace(safe, max_join_gap_mm=3, mode="aggressive")
    letters = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 4.5), word_index=0),
    ]
    blocked = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(4.5, 10), Point(6, 10)], False, 1, "б", 0),
            PlotterStroke(2, [Point(3.25, 9), Point(3.25, 11)], False),
        ],
        [],
    )
    punctuation = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(2.5, 10), Point(3, 10)], False, 1, ".", 0),
        ],
        [],
    )

    _, collision_metrics = route_words(blocked, letters, aggressive)
    _, punctuation_metrics = route_words(
        punctuation,
        [
            replace(_glyph("а", 0, 0), word_index=0),
            replace(_glyph(".", 1, 2.5), word_index=0),
        ],
        aggressive,
    )

    assert collision_metrics["rejections_by_reason"] == {"collision": 1}
    assert punctuation_metrics["rejections_by_reason"] == {"punctuation_rule": 1}
