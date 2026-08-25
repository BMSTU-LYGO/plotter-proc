import math
from pathlib import Path

from plotter_processor.handwriting import JoiningConfig, route_words
from plotter_processor.models import (
    PathDocument,
    PlotterStroke,
    Point,
    PositionedGlyph,
)

CORPUS = Path("tests/fixtures/joining/handwriting_2_russian.txt")


def _config(mode: str = "safe") -> JoiningConfig:
    return JoiningConfig(
        True,
        2.5 if mode == "safe" else 3.75,
        135,
        0.12,
        frozenset(),
        frozenset(),
        True,
        mode=mode,
        max_vertical_offset_mm=2.0,
        min_corridor_inside_ratio=0.7,
    )


def _geometry() -> tuple[PathDocument, list[PositionedGlyph]]:
    glyphs: list[PositionedGlyph] = []
    strokes: list[PlotterStroke] = []
    glyph_index = 0
    for line_index, line in enumerate(CORPUS.read_text(encoding="utf-8").splitlines()):
        cursor = 2.0
        baseline = 8.0 + line_index * 6.0
        for word_index, word in enumerate(line.split()):
            for char in word:
                glyphs.append(
                    PositionedGlyph(
                        char,
                        ord(char),
                        char,
                        cursor,
                        baseline,
                        1.8,
                        0.01,
                        line_index,
                        glyph_index,
                        word_index=word_index,
                    )
                )
                rise = ((ord(char) % 5) - 2) * 0.04
                strokes.append(
                    PlotterStroke(
                        glyph_index,
                        [Point(cursor, baseline), Point(cursor + 1.4, baseline + rise)],
                        False,
                        glyph_index,
                        char,
                        0,
                        source_glyph_indices=(glyph_index,),
                        source_chars=char,
                        segment_types=("glyph",),
                        word_index=word_index,
                    )
                )
                cursor += 1.8
                glyph_index += 1
            cursor += 1.0
    return PathDocument(140, 30, strokes, []), glyphs


def test_handwriting_2_corpus_has_required_cyrillic_and_pair_coverage() -> None:
    text = CORPUS.read_text(encoding="utf-8")

    assert 16 <= len(text.split()) <= 24
    assert set("ъьыжфтлмя") <= set(text)
    assert all(pair in text for pair in ("ст", "ов", "пр", "ть", "ло", "ро", "на", "по"))


def test_handwriting_2_corpus_is_safe_deterministic_and_saves_lifts() -> None:
    document, glyphs = _geometry()

    first, first_metrics = route_words(document, glyphs, _config())
    second, second_metrics = route_words(document, glyphs, _config())
    aggressive, aggressive_metrics = route_words(document, glyphs, _config("aggressive"))

    assert first == second
    assert first_metrics == second_metrics
    assert first_metrics["connected_pairs"] > 0
    assert first_metrics["pen_lifts_inside_words_after"] < first_metrics[
        "pen_lifts_inside_words_before"
    ]
    assert first_metrics["pair_rules_applied"] >= 8
    assert first_metrics["kerning_max_offset_mm"] <= 0.15
    assert aggressive_metrics["connected_pairs"] >= first_metrics["connected_pairs"]
    for result in (first, aggressive):
        assert result.strokes
        assert all(len(stroke.points) >= 2 for stroke in result.strokes)
        assert all(
            math.isfinite(value) and 0 <= value <= limit
            for stroke in result.strokes
            for point in stroke.points
            for value, limit in ((point.x, result.page_width_mm), (point.y, result.page_height_mm))
        )
