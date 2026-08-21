from dataclasses import replace
from pathlib import Path

import pytest

from plotter_processor.handwriting import JoiningConfig, load_joining_config, route_words
from plotter_processor.models import PathDocument, PlotterStroke, Point, PositionedGlyph


def _glyph(char: str, index: int, x: float, *, word: int = 0, baseline: float = 10) -> PositionedGlyph:
    return PositionedGlyph(
        char, ord(char), char, x, baseline, 2, 0.01, 0, index, word_index=word
    )


def _config(**changes: object) -> JoiningConfig:
    config = JoiningConfig(
        True,
        2.5,
        135,
        0.1,
        frozenset(".,!?:;)") ,
        frozenset("(«-"),
        True,
        max_vertical_offset_mm=2.0,
    )
    return replace(config, **changes)


def _pair(
    left: list[Point],
    right: list[Point],
    *,
    left_char: str = "а",
    right_char: str = "б",
    extra: list[PlotterStroke] | None = None,
    different_words: bool = False,
) -> tuple[PathDocument, list[PositionedGlyph]]:
    strokes = [
        PlotterStroke(0, left, False, 0, left_char, 0),
        PlotterStroke(1, right, False, 1, right_char, 0),
        *(extra or []),
    ]
    glyphs = [
        _glyph(left_char, 0, left[0].x, word=0),
        _glyph(right_char, 1, right[0].x, word=1 if different_words else 0),
    ]
    return PathDocument(30, 20, strokes, []), glyphs


def _route(
    left: list[Point], right: list[Point], *, config: JoiningConfig | None = None, **kwargs
):
    document, glyphs = _pair(left, right, **kwargs)
    return route_words(document, glyphs, config or _config())


def test_normal_pair_uses_safe_connector() -> None:
    result, metrics = _route(
        [Point(0, 10), Point(2, 10)], [Point(2.5, 10), Point(4, 10)]
    )
    assert metrics["accepted"] == 1
    assert metrics["snapped_existing_contact"] == 0
    assert "connector" in result.strokes[0].segment_types


def test_existing_contact_is_snapped_without_synthetic_connector() -> None:
    result, metrics = _route(
        [Point(0, 10), Point(2, 10)], [Point(2.04, 10), Point(4, 10)]
    )
    assert metrics["accepted"] == 1
    assert metrics["snapped_existing_contact"] == 1
    assert metrics["connector_length_mm"] == 0
    assert "snap" in result.strokes[0].segment_types


def test_distant_pair_keeps_pen_lift() -> None:
    _, metrics = _route(
        [Point(0, 10), Point(2, 10)], [Point(5, 10), Point(7, 10)]
    )
    assert metrics["accepted"] == 0
    assert metrics["rejected_distance"] == 1


def test_large_vertical_offset_keeps_pen_lift() -> None:
    _, metrics = _route(
        [Point(0, 10), Point(2, 10)], [Point(2.5, 6), Point(4, 6)],
        config=_config(max_join_gap_mm=6),
    )
    assert metrics["accepted"] == 0
    assert metrics["rejections_by_reason"]["vertical_offset"] == 1


def test_tangent_mismatch_keeps_pen_lift() -> None:
    _, metrics = _route(
        [Point(0, 10), Point(2, 10)], [Point(2.5, 10), Point(4, 11)],
        config=_config(max_join_angle_deg=20),
    )
    assert metrics["accepted"] == 0
    assert metrics["rejected_tangent"] == 1


def test_collision_with_secondary_stroke_keeps_pen_lift() -> None:
    obstacle = PlotterStroke(
        2, [Point(2.25, 9.7), Point(2.25, 10.3)], False, 0, "а", 1
    )
    _, metrics = _route(
        [Point(0, 10), Point(2, 10)],
        [Point(2.5, 10), Point(4, 10)],
        extra=[obstacle],
        config=_config(collision_clearance_mm=0.12),
    )
    assert metrics["accepted"] == 0
    assert metrics["rejected_collision"] == 1


def test_bad_corridor_keeps_pen_lift() -> None:
    _, metrics = _route(
        [Point(0, 10), Point(2, 11)],
        [Point(2.5, 10), Point(4, 10)],
        config=_config(
            max_join_angle_deg=180,
            min_corridor_inside_ratio=1.0,
            outside_ink_margin_mm=0.001,
            collision_clearance_mm=0.001,
        ),
    )
    assert metrics["accepted"] == 0
    assert metrics["rejected_corridor"] == 1


def test_connector_does_not_cross_diacritic() -> None:
    diacritic = PlotterStroke(
        2, [Point(2.25, 9.85), Point(2.3, 9.85)], False, 0, "ё", 1
    )
    result, metrics = _route(
        [Point(0, 10), Point(2, 10)],
        [Point(2.5, 10), Point(4, 10)],
        left_char="ё",
        extra=[diacritic],
        config=_config(collision_clearance_mm=0.2),
    )
    assert metrics["rejected_collision"] == 1
    assert any(stroke.contour_index == 1 for stroke in result.strokes)


def test_yo_and_short_i_keep_secondary_strokes() -> None:
    for char in ("ё", "й"):
        mark = PlotterStroke(2, [Point(1, 8), Point(1.2, 8)], False, 0, char, 1)
        result, _ = _route(
            [Point(0, 10), Point(2, 10)],
            [Point(2.5, 10), Point(4, 10)],
            left_char=char,
            extra=[mark],
        )
        assert any(stroke.contour_index == 1 for stroke in result.strokes)


def test_words_and_punctuation_are_never_bridged() -> None:
    _, words = _route(
        [Point(0, 10), Point(2, 10)],
        [Point(2.2, 10), Point(4, 10)],
        different_words=True,
    )
    _, punctuation = _route(
        [Point(0, 10), Point(2, 10)],
        [Point(2.2, 10), Point(3, 10)],
        right_char=",",
    )
    assert words["accepted"] == 0
    assert punctuation["accepted"] == 0
    assert punctuation["rejections_by_reason"]["punctuation_rule"] == 1


def test_backward_connector_is_rejected() -> None:
    _, metrics = _route(
        [Point(0, 10), Point(3, 10)], [Point(2.5, 10), Point(4, 10)]
    )
    assert metrics["accepted"] == 0
    assert metrics["rejections_by_reason"]["backward_motion"] == 1


def test_connection_result_and_debug_are_deterministic() -> None:
    document, glyphs = _pair(
        [Point(0, 10), Point(2, 10)], [Point(2.5, 10), Point(4, 10)]
    )
    first, first_metrics = route_words(document, glyphs, _config())
    second, second_metrics = route_words(document, glyphs, _config())
    assert first.strokes == second.strokes
    assert first.metadata["connection_debug"] == second.metadata["connection_debug"]
    assert first_metrics == second_metrics


def test_problem_word_corpus_has_required_coverage() -> None:
    text = Path("tests/fixtures/joining/problem_words.txt").read_text(encoding="utf-8")
    assert 30 <= len(text.split()) <= 50
    assert set("ъьыйё") <= set(text)
    assert set(".,!?;-()«»") <= set(text)


def test_canonical_connection_config_loads_corridor_and_collision_values() -> None:
    config = load_joining_config(
        {
            "connections": {
                "enabled": True,
                "mode": "safe",
                "connector_step_mm": 0.2,
                "min_corridor_inside_ratio": 0.8,
                "outside_ink_margin_mm": 0.25,
                "collision_clearance_mm": 0.12,
            }
        }
    )
    assert config.min_corridor_inside_ratio == 0.8
    assert config.outside_ink_margin_mm == 0.25
    assert config.collision_clearance_mm == 0.12


def test_legacy_joining_config_is_only_a_warned_compatibility_alias() -> None:
    root = {
        "handwriting": {
            "joining": {"enabled": True, "mode": "safe", "connector_step_mm": 0.2}
        }
    }
    with pytest.warns(UserWarning, match="deprecated"):
        config = load_joining_config(root)
    assert config.enabled is True
