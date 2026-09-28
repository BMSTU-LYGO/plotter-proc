from dataclasses import replace
from itertools import pairwise
from pathlib import Path

from plotter_processor import handwriting
from plotter_processor.handwriting import (
    JoiningConfig,
    PairConnectionRule,
    StrokeThicknessConfig,
    VariationConfig,
    _collision_points,
    _ConnectionCounters,
    _SegmentObstacleIndex,
    apply_handwriting_kerning,
    apply_stroke_thickness_variation,
    apply_variation,
    apply_word_width_variation,
    build_variation_context,
    connection_pair_rule,
    export_handwriting_debug,
    finalize_handwriting_transforms,
    load_variation_config,
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


def test_variation_context_is_deterministic_and_seeded() -> None:
    glyphs = [_glyph("а", index, float(index)) for index in range(12)]
    first = build_variation_context(
        glyphs, VariationConfig(True, 7, 0.1, 1, 2, 0.1)
    )
    repeated = build_variation_context(
        glyphs, VariationConfig(True, 7, 0.1, 1, 2, 0.1)
    )
    changed = build_variation_context(
        glyphs, VariationConfig(True, 8, 0.1, 1, 2, 0.1)
    )

    assert first == repeated
    assert first != changed
    variants = [first.for_glyph(index).glyph_variant for index in range(12)]
    assert len(set(variants)) >= 5
    assert all(left != right for left, right in pairwise(variants))
    assert all(
        variant not in variants[max(0, index - 3) : index]
        for index, variant in enumerate(variants)
    )


def test_handwriting_variation_config_loads_bounded_nested_ranges() -> None:
    config = load_variation_config(
        {
            "handwriting": {
                "variation": {
                    "enabled": True,
                    "seed": 123,
                    "baseline_jitter_mm": 0.1,
                    "rotation_deg": 1.0,
                    "scale_percent": 2.0,
                    "spacing_jitter_mm": 0.1,
                    "letter": {
                        "slant": 99.0,
                        "height_percent": 99.0,
                        "width_percent": 99.0,
                        "y_offset_mm": 99.0,
                    },
                    "word": {"width_percent": 99.0},
                    "line": {"drift_mm": 99.0},
                    "stroke_thickness": {
                        "enabled": True,
                        "probability": 0.9,
                        "offset_mm": 1.0,
                    },
                }
            }
        }
    )

    assert config.seed == 123
    assert config.letter_slant == 0.08
    assert config.letter_height_percent == 6.0
    assert config.letter_width_percent == 6.0
    assert config.letter_y_offset_mm == 0.25
    assert config.word_width_percent == 5.0
    assert config.line_drift_mm == 0.35
    assert config.stroke_thickness.probability == 0.35
    assert config.stroke_thickness.offset_mm == 0.04


def test_strong_variation_profile_is_enabled_and_uses_wider_safe_ranges() -> None:
    config = load_variation_config(
        {
            "handwriting": {
                "variation": {
                    "enabled": True,
                    "realism": "strong",
                    "seed": 123,
                    "baseline_jitter_mm": 0.3,
                    "rotation_deg": 4.0,
                    "scale_percent": 8.0,
                    "spacing_jitter_mm": 0.1,
                    "letter": {
                        "slant": 0.14,
                        "height_percent": 10.0,
                        "width_percent": 12.0,
                        "y_offset_mm": 0.3,
                    },
                    "word": {"width_percent": 10.0},
                    "line": {"drift_mm": 0.45},
                    "stroke_thickness": {
                        "enabled": False,
                        "probability": 0.0,
                        "offset_mm": 0.0,
                    },
                }
            }
        }
    )

    assert config.enabled is True
    assert config.realism == "strong"
    assert config.letter_width_percent == 12.0
    assert config.letter_height_percent == 10.0
    assert config.rotation_deg == 4.0
    assert config.word_width_percent == 10.0


def test_local_shape_warp_is_smooth_deterministic_and_preserves_endpoints() -> None:
    glyph = _glyph("о", 0, 2)
    stroke = PlotterStroke(
        0,
        [
            Point(2.0, 10.0),
            Point(2.2, 9.2),
            Point(3.0, 8.8),
            Point(3.8, 9.2),
            Point(4.0, 10.0),
        ],
        False,
        0,
        "о",
        0,
    )
    document = PathDocument(20, 20, [stroke], [])
    config = VariationConfig(True, 17, 0, 0, 0, 0, realism="strong")

    first = apply_variation(document, [glyph], config)
    repeated = apply_variation(document, [glyph], config)
    normal = apply_variation(
        document, [glyph], replace(config, realism="normal")
    )

    assert first.strokes[0].points == repeated.strokes[0].points
    assert first.strokes[0].points[0] == stroke.points[0]
    assert first.strokes[0].points[-1] == stroke.points[-1]
    assert first.strokes[0].points[1:-1] != stroke.points[1:-1]
    assert first.strokes[0].points[1:-1] != normal.strokes[0].points[1:-1]


def test_repeated_glyphs_receive_readable_local_variants() -> None:
    glyphs = [_glyph("а", index, float(index * 2)) for index in range(8)]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(
                index,
                [Point(glyph.x_mm, 9), Point(glyph.x_mm + 1, 11)],
                False,
                glyph.glyph_index,
                glyph.char,
                0,
            )
            for index, glyph in enumerate(glyphs)
        ],
        [],
    )
    config = VariationConfig(True, 7, 0, 0, 0, 0)

    result = apply_variation(document, glyphs, config)
    relative_shapes = {
        tuple((round(point.x - glyph.x_mm, 4), round(point.y - 10, 4)) for point in stroke.points)
        for glyph, stroke in zip(glyphs, result.strokes, strict=True)
    }

    assert len(relative_shapes) >= 5
    variants = result.metadata["glyph_variants"]
    assert len(set(variants.values())) >= 5


def test_procedural_glyph_variants_are_cached_by_character_variant_and_style() -> None:
    handwriting._GLYPH_VARIANT_CACHE.clear()
    glyphs = [_glyph("а", index, float(index * 2)) for index in range(40)]
    document = PathDocument(
        100,
        20,
        [
            PlotterStroke(
                index,
                [
                    Point(glyph.x_mm, 10),
                    Point(glyph.x_mm + 0.3, 9),
                    Point(glyph.x_mm + 1.0, 8.7),
                    Point(glyph.x_mm + 1.7, 9),
                    Point(glyph.x_mm + 2.0, 10),
                ],
                False,
                index,
                glyph.char,
                0,
            )
            for index, glyph in enumerate(glyphs)
        ],
        [],
    )
    config = VariationConfig(True, 91, 0, 0, 0, 0, realism="strong")

    first = apply_variation(document, glyphs, config)
    repeated = apply_variation(document, glyphs, config)

    assert first.metadata["glyph_variant_cache"]["hits"] > 0
    assert repeated.metadata["glyph_variant_cache"]["hits"] == len(glyphs)
    assert first.strokes == repeated.strokes


def test_strong_repeated_glyph_fixture_has_natural_normalized_geometry() -> None:
    text = Path("tests/fixtures/handwriting/repeated_glyphs.txt").read_text(
        encoding="utf-8"
    )
    characters = [char for char in text if char.isalpha()]
    glyphs = [
        replace(_glyph(char, index, 3.0 + index * 2.2), word_index=index // 5)
        for index, char in enumerate(characters)
    ]
    strokes = [
        PlotterStroke(
            index,
            [
                Point(glyph.x_mm, 10.0),
                Point(glyph.x_mm + 0.25, 9.15),
                Point(glyph.x_mm + 0.9, 8.75),
                Point(glyph.x_mm + 1.55, 9.20),
                Point(glyph.x_mm + 1.8, 10.0),
            ],
            False,
            index,
            glyph.char,
            0,
        )
        for index, glyph in enumerate(glyphs)
    ]
    document = PathDocument(len(glyphs) * 2.2 + 8, 20, strokes, [])
    config = VariationConfig(
        True,
        121,
        0.12,
        3.0,
        7.0,
        0.08,
        letter_slant=0.10,
        letter_height_percent=9.0,
        letter_width_percent=10.0,
        letter_y_offset_mm=0.22,
        word_width_percent=8.0,
        line_drift_mm=0.16,
        realism="strong",
    )

    first = apply_variation(document, glyphs, config)
    repeated = apply_variation(document, glyphs, config)
    changed = apply_variation(document, glyphs, replace(config, seed=122))

    def normalized(stroke: PlotterStroke) -> tuple[tuple[float, float], ...]:
        min_x, min_y, max_x, max_y = handwriting._stroke_bounds(stroke)
        width = max(max_x - min_x, 1e-9)
        height = max(max_y - min_y, 1e-9)
        return tuple(
            (round((point.x - min_x) / width, 4), round((point.y - min_y) / height, 4))
            for point in stroke.points
        )

    shapes_by_char = {
        char: {
            normalized(stroke)
            for stroke in first.strokes
            if stroke.char == char
        }
        for char in set(characters)
    }
    repeated_chars = {char for char in set(characters) if characters.count(char) >= 4}

    assert all(len(shapes_by_char[char]) >= 3 for char in repeated_chars)
    assert len(set(first.metadata["glyph_variants"].values())) >= 6
    assert first.strokes == repeated.strokes
    assert first.strokes != changed.strokes
    assert len(first.strokes) == len(document.strokes)
    assert all(
        0 <= point.x <= first.page_width_mm and 0 <= point.y <= first.page_height_mm
        for stroke in first.strokes
        for point in stroke.points
    )


def test_connector_shape_variation_is_seeded_bounded_and_keeps_one_pass() -> None:
    glyphs = [
        replace(_glyph("м", 0, 0), word_index=0),
        replace(_glyph("а", 1, 2.5), word_index=0),
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "м", 0),
            PlotterStroke(1, [Point(2.5, 10), Point(4.5, 10)], False, 1, "а", 0),
        ],
        [],
    )
    config = replace(
        _config(), variation_seed=211, connector_shape_variation=1.0
    )

    first, first_metrics = route_words(document, glyphs, config)
    repeated, repeated_metrics = route_words(document, glyphs, config)
    changed, changed_metrics = route_words(
        document, glyphs, replace(config, variation_seed=212)
    )

    assert first.strokes == repeated.strokes
    assert first.strokes != changed.strokes
    assert first_metrics["joins_created"] == repeated_metrics["joins_created"] == 1
    assert changed_metrics["joins_created"] == 1
    assert len(first.strokes) == len(changed.strokes) == 1
    assert all(
        right.x >= left.x - 0.15
        for left, right in pairwise(first.strokes[0].points)
    )


def test_glyph_scale_variation_is_independent_small_and_post_layout() -> None:
    glyphs = [_glyph("а", index, float(index * 3)) for index in range(8)]
    original_positions = [(glyph.x_mm, glyph.baseline_y_mm) for glyph in glyphs]

    context = build_variation_context(
        glyphs, VariationConfig(True, 11, 0, 0, 20, 0)
    )

    scales = [context.for_glyph(index) for index in range(len(glyphs))]
    assert all(0.97 <= item.scale_x <= 1.03 for item in scales)
    assert all(0.97 <= item.scale_y <= 1.03 for item in scales)
    assert any(item.scale_x != item.scale_y for item in scales)
    assert [(glyph.x_mm, glyph.baseline_y_mm) for glyph in glyphs] == original_positions


def test_glyph_geometry_gets_width_height_slant_and_y_offset() -> None:
    glyph = _glyph("и", 0, 5)
    document = PathDocument(
        20,
        20,
        [PlotterStroke(0, [Point(5, 8), Point(6, 10)], False, 0, "и", 0)],
        [],
    )
    config = VariationConfig(
        True,
        19,
        0,
        0,
        0,
        0,
        letter_slant=0.05,
        letter_height_percent=6,
        letter_width_percent=6,
        letter_y_offset_mm=0.2,
    )

    context = build_variation_context([glyph], config)
    result = apply_variation(document, [glyph], config)
    transform = context.for_glyph(0)

    assert transform.scale_x != 1.0
    assert transform.scale_y != 1.0
    assert transform.variant_slant != 0.0
    assert transform.baseline_offset_mm != 0.0
    assert result.strokes[0].points != document.strokes[0].points


def test_transformed_glyphs_remain_connectable() -> None:
    glyphs = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 2.2), word_index=0),
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(2.2, 10), Point(4, 10)], False, 1, "б", 0),
        ],
        [],
    )
    varied = apply_variation(
        document,
        glyphs,
        VariationConfig(True, 23, 0.05, 0.5, 2, 0),
    )

    connected, metrics = route_words(varied, glyphs, _config())

    assert metrics["joins_created"] == 1
    assert len(connected.strokes) == 1


def test_rotation_and_baseline_variation_stay_inside_safe_limits() -> None:
    glyphs = [
        _glyph("а", index, float(index * 2), line=index // 4) for index in range(8)
    ]
    glyphs = [
        replace(glyph, baseline_y_mm=10.0 + glyph.line_index * 4.0)
        for glyph in glyphs
    ]
    context = build_variation_context(
        glyphs, VariationConfig(True, 21, 5.0, 10.0, 0, 0)
    )

    variations = context.glyphs.values()
    assert all(abs(item.rotation_deg) <= 2.0 for item in variations)
    assert all(abs(item.baseline_offset_mm) <= 0.12 for item in variations)

    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(
                index,
                [
                    Point(glyph.x_mm, glyph.baseline_y_mm - 1),
                    Point(glyph.x_mm + 1, glyph.baseline_y_mm + 1),
                ],
                False,
                glyph.glyph_index,
                glyph.char,
                0,
            )
            for index, glyph in enumerate(glyphs)
        ],
        [],
    )
    result = apply_variation(
        document, glyphs, VariationConfig(True, 21, 5.0, 10.0, 0, 0)
    )
    first_line = [point.y for stroke in result.strokes[:4] for point in stroke.points]
    second_line = [point.y for stroke in result.strokes[4:] for point in stroke.points]

    assert max(first_line) < min(second_line)


def test_word_variation_is_shared_and_glyph_variation_is_weaker() -> None:
    glyphs = [
        replace(_glyph(char, index, float(index * 2)), word_index=word)
        for index, (char, word) in enumerate(
            [("м", 0), ("а", 0), ("м", 0), ("а", 1), ("м", 1), ("а", 1)]
        )
    ]
    config = VariationConfig(True, 31, 0.15, 1.0, 2.0, 0.1)

    context = build_variation_context(glyphs, config)

    assert set(context.words) == {(0, 0), (0, 1)}
    first_word = context.words[(0, 0)]
    second_word = context.words[(0, 1)]
    assert first_word != second_word
    assert abs(first_word.rotation_deg) <= 0.4
    assert abs(first_word.scale_x_delta) <= 0.008
    assert abs(first_word.baseline_offset_mm) <= 0.06


def test_word_width_scales_completed_word_and_connector_only_on_x() -> None:
    glyphs = [
        replace(_glyph("а", 0, 1), word_index=0),
        replace(_glyph("б", 1, 3), word_index=0),
    ]
    connector = PlotterStroke(
        0,
        [Point(1, 9), Point(2, 10), Point(4, 11)],
        False,
        0,
        "аб",
        0,
        source_glyph_indices=(0, 1),
        segment_types=("glyph", "connector", "glyph"),
    )
    document = PathDocument(20, 20, [connector], [])
    config = VariationConfig(True, 37, 0, 0, 0, 0, word_width_percent=5)

    result = apply_word_width_variation(document, glyphs, config)

    before = connector.points
    after = result.strokes[0].points
    assert [point.y for point in after] == [point.y for point in before]
    assert after[1].x != before[1].x
    assert result.metadata["word_width_factors"]["0:0"] != 1.0


def test_visual_thickness_is_light_deterministic_and_disabled_in_superfast() -> None:
    document = PathDocument(
        30,
        20,
        [
            PlotterStroke(
                index,
                [Point(index * 2.0, 10), Point(index * 2.0 + 1, 9)],
                False,
                index,
                "а",
                0,
            )
            for index in range(10)
        ],
        [],
    )
    config = VariationConfig(
        True,
        61,
        0,
        0,
        0,
        0,
        stroke_thickness=StrokeThicknessConfig(True, 0.3, 0.025),
    )

    first = apply_stroke_thickness_variation(document, config)
    repeated = apply_stroke_thickness_variation(document, config)
    superfast = apply_stroke_thickness_variation(document, config, path_mode="superfast")

    retraced = first.metadata["stroke_thickness_variation"]["retraced_strokes"]
    assert 0 < retraced < len(document.strokes)
    assert first.strokes == repeated.strokes
    assert all(len(stroke.points) <= 4 for stroke in first.strokes)
    assert superfast is document


def test_final_handwriting_validation_clamps_word_and_page_bounds() -> None:
    glyphs = [replace(_glyph("а", 0, 0), word_index=0)]
    reference = PathDocument(
        10,
        10,
        [PlotterStroke(0, [Point(0.2, 4), Point(1.2, 6)], False, 0, "а", 0)],
        [],
    )
    transformed = PathDocument(
        10,
        10,
        [PlotterStroke(0, [Point(-1, 3), Point(3, 7)], False, 0, "а", 0)],
        [],
    )

    result = finalize_handwriting_transforms(
        transformed, glyphs, reference=reference, keep_out_zones=[]
    )
    points = result.strokes[0].points

    assert all(0 <= point.x <= 10 and 0 <= point.y <= 10 for point in points)
    assert max(point.x for point in points) - min(point.x for point in points) <= 1.08
    assert result.metadata["handwriting_validation"]["clamped_words"] == 1


def test_small_russian_fixture_is_reproducible_and_changes_across_seeds() -> None:
    text = "приветпривет"
    glyphs = [
        replace(
            _glyph(char, index, 5.0 + index * 2.0),
            word_index=0 if index < 6 else 1,
        )
        for index, char in enumerate(text)
    ]
    reference = PathDocument(
        40,
        20,
        [
            PlotterStroke(
                index,
                [Point(glyph.x_mm, 10), Point(glyph.x_mm + 1.5, 9)],
                False,
                index,
                glyph.char,
                0,
            )
            for index, glyph in enumerate(glyphs)
        ],
        [],
    )

    def render(seed: int) -> PathDocument:
        config = VariationConfig(
            True,
            seed,
            0.12,
            1.0,
            2.0,
            0,
            letter_slant=0.035,
            letter_height_percent=4,
            letter_width_percent=4,
            letter_y_offset_mm=0.15,
            word_width_percent=3,
            line_drift_mm=0.12,
        )
        varied = apply_variation(reference, glyphs, config)
        varied = apply_word_width_variation(varied, glyphs, config)
        return finalize_handwriting_transforms(
            varied,
            glyphs,
            reference=reference,
            keep_out_zones=[
                {"x_mm": 1.0, "y_mm": 1.0, "radius_mm": 0.2, "clearance_mm": 0.1}
            ],
        )

    first = render(71)
    repeated = render(71)
    changed = render(72)

    assert [stroke.points for stroke in first.strokes] == [
        stroke.points for stroke in repeated.strokes
    ]
    assert [stroke.points for stroke in first.strokes] != [
        stroke.points for stroke in changed.strokes
    ]
    assert all(
        0 <= point.x <= first.page_width_mm and 0 <= point.y <= first.page_height_mm
        for stroke in first.strokes
        for point in stroke.points
    )


def test_line_variation_is_correlated_bounded_and_does_not_reflow() -> None:
    glyphs = [
        replace(
            _glyph(char, index, float(column * 2), line=line),
            baseline_y_mm=8.0 + line * 4.0,
            word_index=0,
        )
        for line in range(3)
        for column, (index, char) in enumerate(
            ((line * 3, "м"), (line * 3 + 1, "а"), (line * 3 + 2, "м"))
        )
    ]
    config = VariationConfig(True, 41, 0.15, 1.0, 2.0, 0)
    context = build_variation_context(glyphs, config)

    assert set(context.lines) == {0, 1, 2}
    assert len(set(context.lines.values())) == 3
    assert all(abs(line.rotation_deg) <= 0.2 for line in context.lines.values())
    assert all(
        abs(line.baseline_offset_mm) <= 0.018
        for line in context.lines.values()
    )
    assert all(
        abs(line.baseline_drift_mm) <= 0.024 for line in context.lines.values()
    )

    original_layout = [
        (glyph.x_mm, glyph.baseline_y_mm, glyph.line_index) for glyph in glyphs
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(
                index,
                [
                    Point(glyph.x_mm, glyph.baseline_y_mm - 1),
                    Point(glyph.x_mm + 1, glyph.baseline_y_mm + 1),
                ],
                False,
                glyph.glyph_index,
                glyph.char,
                0,
            )
            for index, glyph in enumerate(glyphs)
        ],
        [],
    )
    result = apply_variation(document, glyphs, config)

    assert [
        (glyph.x_mm, glyph.baseline_y_mm, glyph.line_index) for glyph in glyphs
    ] == original_layout
    line_ranges = [
        [point.y for stroke in result.strokes[start : start + 3] for point in stroke.points]
        for start in (0, 3, 6)
    ]
    assert max(line_ranges[0]) < min(line_ranges[1])
    assert max(line_ranges[1]) < min(line_ranges[2])


def test_letter_variation_changes_smoothly_within_a_line() -> None:
    glyphs = [
        replace(_glyph(chr(ord("а") + index), index, index * 2.0), word_index=index // 3)
        for index in range(12)
    ]
    config = VariationConfig(
        True,
        53,
        0,
        0,
        0,
        0,
        letter_slant=0.06,
        letter_height_percent=6,
        letter_width_percent=6,
        letter_y_offset_mm=0.2,
        word_width_percent=4,
        line_drift_mm=0.1,
    )

    context = build_variation_context(glyphs, config)
    ordered = [context.for_glyph(index) for index in range(len(glyphs))]

    assert all(
        abs(right.scale_x - left.scale_x) < 0.045
        for left, right in pairwise(ordered)
    )
    assert all(
        abs(right.scale_y - left.scale_y) < 0.045
        for left, right in pairwise(ordered)
    )
    assert all(
        abs(right.variant_slant - left.variant_slant) < 0.05
        for left, right in pairwise(ordered)
    )


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


def test_segment_index_keeps_giant_stroke_out_of_grid_without_losing_it() -> None:
    giant = PlotterStroke(0, [Point(0, 0), Point(100_000, 0)], False)
    nearby = PlotterStroke(1, [Point(10, 10), Point(11, 10)], False)

    index = _SegmentObstacleIndex.build([giant, nearby], cell_size_mm=4)

    assert index.unindexed_strokes == (0,)
    assert len(index.cells) <= handwriting._MAX_SPATIAL_INDEX_CELLS_PER_BOUNDS
    assert [item.stroke.id for item in index.query((99_999, -1, 100_001, 1))] == [0]

    giant_segments = index.segment_cache[0]
    assert giant_segments.unindexed_segments == (0,)
    assert len(giant_segments.cells) <= handwriting._MAX_SPATIAL_INDEX_CELLS_PER_BOUNDS


def test_collision_checks_query_only_segments_near_each_curve_sample() -> None:
    left = PlotterStroke(0, [Point(-1, 0), Point(0, 0)], False)
    right = PlotterStroke(1, [Point(10, 10), Point(11, 10)], False)
    collision = PlotterStroke(2, [Point(4.9, 5), Point(5.1, 5)], False)
    distant = [
        PlotterStroke(
            index + 3,
            [Point(index / 10, 8), Point(index / 10 + 0.05, 8)],
            False,
        )
        for index in range(100)
    ]
    counters = _ConnectionCounters()

    collisions = _collision_points(
        [Point(0, 0), Point(5, 5), Point(10, 10)],
        _SegmentObstacleIndex.build([left, right, collision, *distant]),
        left,
        right,
        Point(0, 0),
        Point(10, 10),
        0.1,
        counters,
    )

    assert collisions == [Point(5, 5)]
    assert counters.segments_tested == 1


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
    assert metrics["solver_calls"] == 0
    assert metrics["beziers_built"] == 0
    assert metrics["collision_queries"] == 0
    assert metrics["segments_tested"] == 0
    assert "connection_debug" not in result.metadata


def test_pair_rule_can_adjust_spacing_and_connector_shape() -> None:
    config = replace(
        _config(),
        pair_rules=(PairConnectionRule("ст", -0.1, 1.15, 0.03),),
    )

    rule = connection_pair_rule("С", "т", config)

    assert rule == PairConnectionRule("ст", -0.1, 1.15, 0.03)
    assert connection_pair_rule("а", "б", config) is None


def test_handwriting_kerning_uses_ink_gap_and_stays_bounded() -> None:
    glyphs = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 2.8), word_index=0),
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(2.8, 10), Point(4, 10)], False, 1, "б", 0),
        ],
        [],
    )

    adjusted, positioned, metrics = apply_handwriting_kerning(
        document, glyphs, _config()
    )

    assert adjusted.page_width_mm == document.page_width_mm
    assert adjusted.strokes[1].points[0].x < document.strokes[1].points[0].x
    assert positioned[1].x_mm < glyphs[1].x_mm
    assert metrics["kerning_pairs_adjusted"] == 1
    assert 0 < metrics["kerning_max_offset_mm"] <= 0.15


def test_handwriting_kerning_separates_overlapping_ink() -> None:
    glyphs = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 1.8), word_index=0),
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(1.8, 10), Point(4, 10)], False, 1, "б", 0),
        ],
        [],
    )

    adjusted, _, metrics = apply_handwriting_kerning(document, glyphs, _config())

    assert adjusted.strokes[1].points[0].x > document.strokes[1].points[0].x
    assert metrics["kerning_pairs_adjusted"] == 1


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


def test_aggressive_can_join_terminal_anchors_with_backward_tangents() -> None:
    glyphs = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 2), word_index=0),
    ]
    document = PathDocument(
        20,
        20,
        [
            PlotterStroke(
                0, [Point(0, 10), Point(1, 9), Point(0.2, 10)], False, 0, "а", 0
            ),
            PlotterStroke(
                1, [Point(2, 10), Point(1.2, 11), Point(2.2, 10)], False, 1, "б", 0
            ),
        ],
        [],
    )
    safe = _config()
    aggressive = replace(safe, mode="aggressive")

    safe_result, safe_metrics = route_words(document, glyphs, safe)
    aggressive_result, aggressive_metrics = route_words(document, glyphs, aggressive)

    assert len(safe_result.strokes) == 2
    assert safe_metrics["rejections_by_reason"] == {"anchor_not_routeable": 1}
    assert len(aggressive_result.strokes) == 1
    assert aggressive_metrics["joins_created"] == 1


def test_aggressive_ignores_only_connected_glyphs_in_collision_check() -> None:
    glyphs = [
        replace(_glyph("а", 0, 0), word_index=0),
        replace(_glyph("б", 1, 3), word_index=0),
    ]
    connected_geometry = PathDocument(
        20,
        20,
        [
            PlotterStroke(0, [Point(0, 10), Point(2, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(3, 10), Point(2.5, 10), Point(5, 10)], False, 1, "б", 0),
        ],
        [],
    )
    aggressive = replace(_config(), mode="aggressive")

    result, metrics = route_words(connected_geometry, glyphs, aggressive)

    assert len(result.strokes) == 1
    assert metrics["joins_created"] == 1

    foreign_obstacle = PlotterStroke(
        2, [Point(2.25, 9), Point(2.25, 11)], False
    )
    blocked, blocked_metrics = route_words(
        replace(
            connected_geometry,
            strokes=[*connected_geometry.strokes, foreign_obstacle],
        ),
        glyphs,
        aggressive,
    )

    assert len(blocked.strokes) == 3
    assert blocked_metrics["rejections_by_reason"] == {"collision": 1}


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
            replace(
                _glyph(".", 1, 2.5), word_index=0, text_role="punctuation"
            ),
        ],
        aggressive,
    )

    assert collision_metrics["rejections_by_reason"] == {"collision": 1}
    assert punctuation_metrics["words"] == 2
    assert punctuation_metrics["pairs_total"] == 0
    assert punctuation_metrics["rejections_by_reason"] == {}
