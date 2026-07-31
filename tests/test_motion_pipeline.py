import math

import pytest

from plotter_processor.gcode_analyzer import analyze_gcode
from plotter_processor.gcode_exporter import (
    generate_gcode,
    generate_pen_calibration_gcode,
    generate_speed_calibration_gcode,
)
from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.motion_config import apply_motion_profile, resolve_motion_profile
from plotter_processor.motion_statistics import calculate_motion_statistics
from plotter_processor.path_simplifier import simplify_path_document


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
