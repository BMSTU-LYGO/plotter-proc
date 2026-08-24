import math

import pytest

from plotter_processor import path_simplifier
from plotter_processor.gcode_analyzer import analyze_gcode
from plotter_processor.gcode_exporter import (
    generate_gcode,
    generate_pen_calibration_gcode,
    generate_speed_calibration_gcode,
)
from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.motion_config import apply_motion_profile, resolve_motion_profile
from plotter_processor.motion_statistics import calculate_motion_statistics
from plotter_processor.path_simplifier import (
    SimplificationTemplateCache,
    path_complexity,
    simplify_path_document,
)


def _machine() -> dict[str, object]:
    return {
        "page_origin_mm": {"x": 0, "y": 0},
        "axes": {"invert_x": False, "invert_y": False},
        "pen": {"up_z_mm": 5, "down_z_mm": 1, "settle_ms": 100},
        "feedrate_mm_min": {"draw": 60, "travel": 120, "z": 60},
        "workspace_mm": {"min_x": 0, "max_x": 220, "min_y": 0, "max_y": 220},
        "gcode": {"home": False, "absolute_positioning": True, "units_mm": True, "decimals": 3},
    }


def _document() -> PathDocument:
    return PathDocument(
        100,
        100,
        [
            PlotterStroke(0, [Point(10, 10), Point(70, 10)], False, 0, "а", 0),
            PlotterStroke(1, [Point(70, 20), Point(70, 80)], False, 1, "б", 0),
        ],
        [],
    )


def test_motion_statistics_include_draw_travel_z_and_dwell() -> None:
    profile = resolve_motion_profile(_machine())
    stats = calculate_motion_statistics(_document(), profile)
    assert stats["ideal_draw_time_seconds"] == 120
    assert stats["ideal_travel_time_seconds"] == 5
    assert stats["ideal_z_time_seconds"] == 16
    assert stats["dwell_time_seconds"] == 0.2
    assert stats["ideal_total_time_seconds"] == 141.2


def test_zero_settle_and_legacy_settle_priority() -> None:
    machine = _machine()
    machine["pen"] = {"up_z_mm": 5, "down_z_mm": 1, "settle_ms": 100, "down_settle_ms": 0}
    profile = resolve_motion_profile(machine)
    gcode = generate_gcode(_document(), apply_motion_profile(machine, profile))
    assert profile.pen.down_settle_ms == 0
    assert "G4" not in gcode


def test_profiles_and_unknown_profile() -> None:
    machine = _machine()
    machine["motion_profiles"] = {
        "default": "safe",
        "profiles": {
            name: {"pen": {"up_z_mm": 5, "down_z_mm": 1, "down_settle_ms": 0}, "feedrate_mm_min": {"draw": speed, "travel": 120, "z": 60}}
            for name, speed in (("safe", 60), ("balanced", 90), ("fast", 120))
        },
    }
    assert resolve_motion_profile(machine).name == "safe"
    assert resolve_motion_profile(machine, "balanced").feedrate.draw_mm_min == 90
    assert resolve_motion_profile(machine, "fast").name == "fast"
    with pytest.raises(ValueError, match="Available profiles"):
        resolve_motion_profile(machine, "turbo")


def test_simplification_is_bounded_and_preserves_metadata_and_endpoints() -> None:
    points = [Point(x, math.sin(x / 10) * 0.01) for x in range(101)]
    source = PathDocument(100, 100, [PlotterStroke(7, points, False, 2, "ё", 3)], [])
    result, stats = simplify_path_document(source, duplicate_epsilon_mm=0.001, min_segment_length_mm=0.04, max_deviation_mm=0.05)
    stroke = result.strokes[0]
    assert len(stroke.points) < len(points)
    assert stroke.points[0] == points[0] and stroke.points[-1] == points[-1]
    assert (stroke.id, stroke.glyph_index, stroke.char, stroke.contour_index) == (7, 2, "ё", 3)
    assert stats["max_observed_deviation_mm"] <= 0.05


def test_closed_stroke_stays_closed() -> None:
    source = PathDocument(10, 10, [PlotterStroke(0, [Point(1, 1), Point(9, 1), Point(9, 9), Point(1, 9)], True)], [])
    result, _ = simplify_path_document(source, duplicate_epsilon_mm=0, min_segment_length_mm=0, max_deviation_mm=0.01)
    assert result.strokes[0].closed
    assert len(result.strokes[0].points) >= 3


def test_simplification_handles_long_adversarial_stroke_without_recursion() -> None:
    points = [Point(float(index), float(index % 2)) for index in range(1500)]
    source = PathDocument(1600, 10, [PlotterStroke(0, points, False)], [])

    result, stats = simplify_path_document(
        source,
        duplicate_epsilon_mm=0,
        min_segment_length_mm=0,
        max_deviation_mm=0.1,
    )

    assert result.strokes[0].points[0] == points[0]
    assert result.strokes[0].points[-1] == points[-1]
    assert stats["max_observed_deviation_mm"] <= 0.1


def test_vectorized_rdp_matches_scalar_path(monkeypatch: pytest.MonkeyPatch) -> None:
    points = [Point(index / 10, math.sin(index / 11) * 0.2) for index in range(500)]
    source = PathDocument(100, 100, [PlotterStroke(0, points, False)], [])
    monkeypatch.setattr(path_simplifier, "_VECTOR_INTERVAL_THRESHOLD", 10_000)
    scalar, scalar_stats = simplify_path_document(
        source,
        duplicate_epsilon_mm=0,
        min_segment_length_mm=0,
        max_deviation_mm=0.06,
    )
    monkeypatch.setattr(path_simplifier, "_VECTOR_INTERVAL_THRESHOLD", 1)
    vectorized, vectorized_stats = simplify_path_document(
        source,
        duplicate_epsilon_mm=0,
        min_segment_length_mm=0,
        max_deviation_mm=0.06,
    )

    assert vectorized.strokes[0].points == scalar.strokes[0].points
    assert vectorized_stats["max_observed_deviation_mm"] == scalar_stats[
        "max_observed_deviation_mm"
    ]


def test_template_cache_reuses_translated_glyph_and_reports_complexity() -> None:
    points = [Point(index / 10, math.sin(index / 8) * 0.1) for index in range(200)]
    translated = [Point(point.x + 20, point.y + 30) for point in points]
    strokes = [
        PlotterStroke(
            index,
            stroke_points,
            False,
            glyph_index=index,
            char="a",
            contour_index=0,
            source_glyph_indices=(index,),
            source_chars="a",
            segment_types=("glyph",),
        )
        for index, stroke_points in enumerate((points, translated))
    ]
    source = PathDocument(100, 100, strokes, [])
    cache = SimplificationTemplateCache()
    result, stats = simplify_path_document(
        source,
        duplicate_epsilon_mm=0,
        min_segment_length_mm=0,
        max_deviation_mm=0.06,
        template_cache=cache,
        template_identities={0: ("font", "a", 0.01), 1: ("font", "a", 0.01)},
    )

    assert stats["unique_templates_simplified"] == 1
    assert stats["glyph_occurrences_reused"] == 1
    assert stats["dedupe_occurrences_skipped"] == 1
    assert len(result.strokes[0].points) == len(result.strokes[1].points)
    cached_indices = cache.entries[next(iter(cache.entries))][0]
    assert result.strokes[1].points == [translated[index] for index in cached_indices]
    assert stats["complexity_after_route"] == path_complexity(source)
    assert stats["complexity_after_simplification"] == path_complexity(result)


def test_template_cache_does_not_reuse_incompatible_point_sequences() -> None:
    first = [Point(float(index), math.sin(index)) for index in range(100)]
    second = [*first[:-1], Point(98.5, 0.25), first[-1]]
    strokes = [
        PlotterStroke(
            index,
            points,
            False,
            glyph_index=index,
            char="a",
            contour_index=0,
            source_glyph_indices=(index,),
            source_chars="a",
            segment_types=("glyph",),
        )
        for index, points in enumerate((first, second))
    ]
    _, stats = simplify_path_document(
        PathDocument(100, 100, strokes, []),
        duplicate_epsilon_mm=0,
        min_segment_length_mm=0,
        max_deviation_mm=0.06,
        template_cache=SimplificationTemplateCache(),
        template_identities={0: ("font", "a", 0.01), 1: ("font", "a", 0.01)},
    )

    assert stats["unique_templates_simplified"] == 2
    assert stats["glyph_occurrences_reused"] == 0


def test_gcode_analyzer_handles_modal_feedrate() -> None:
    result = analyze_gcode("G21\nG90\nG1 X60 F60\nG1 X120\nG4 P100\nM400\nM84\n")
    assert result["motion_command_count"] == 2
    assert result["dwell_count"] == 1
    assert result["ideal_total_time_seconds"] == 120.1


def test_rounded_duplicate_xy_commands_are_removed() -> None:
    document = PathDocument(10, 10, [PlotterStroke(0, [Point(1, 1), Point(1.0001, 1.0001), Point(2, 2)], False)], [])
    gcode = generate_gcode(document, _machine())
    assert gcode.count("X1.000 Y1.000") == 1


def test_profile_header_and_calibration_are_safe() -> None:
    machine = _machine()
    profile = resolve_motion_profile(machine)
    resolved = apply_motion_profile(machine, profile)
    gcode = generate_gcode(_document(), resolved, motion_profile=profile, motion={"ideal_total_time_seconds": 1})
    assert "; Motion profile: safe" in gcode
    for calibration in (
        generate_speed_calibration_gcode(resolved),
        generate_pen_calibration_gcode(resolved),
    ):
        assert "G28" not in calibration
        assert "G4 P0" not in calibration
        assert all(command not in calibration for command in ("M104", "M109", "M140", "M190"))
        assert calibration.rstrip().splitlines()[-4].startswith("G0 Z")
