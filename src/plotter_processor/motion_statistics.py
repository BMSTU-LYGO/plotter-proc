from __future__ import annotations

import math
import statistics
from itertools import pairwise

from plotter_processor.models import PathDocument
from plotter_processor.motion_config import ResolvedMotionProfile


def calculate_motion_statistics(
    document: PathDocument,
    profile: ResolvedMotionProfile,
    *,
    short_segment_mm: float = 0.20,
    very_short_segment_mm: float = 0.08,
) -> dict[str, object]:
    if short_segment_mm <= 0 or very_short_segment_mm <= 0:
        raise ValueError("motion segment thresholds must be positive")
    strokes = document.strokes
    segments: list[float] = []
    draw = 0.0
    for stroke in strokes:
        pairs = list(pairwise(stroke.points))
        if stroke.closed and stroke.points[-1] != stroke.points[0]:
            pairs.append((stroke.points[-1], stroke.points[0]))
        lengths = [math.hypot(b.x - a.x, b.y - a.y) for a, b in pairs]
        segments.extend(length for length in lengths if length > 0)
        draw += sum(lengths)
    travels = [
        math.hypot(b.points[0].x - a.points[-1].x, b.points[0].y - a.points[-1].y)
        for a, b in pairwise(strokes)
    ]
    travel = sum(travels)
    count = len(strokes)
    z_one_way = profile.pen.up_z_mm - profile.pen.down_z_mm
    z_distance = 2 * count * z_one_way
    dwell_count = count if profile.pen.down_settle_ms else 0
    dwell = dwell_count * profile.pen.down_settle_ms / 1000
    draw_time = draw / profile.feedrate.draw_mm_min * 60
    travel_time = travel / profile.feedrate.travel_mm_min * 60
    z_time = z_distance / profile.feedrate.z_mm_min * 60
    short = sum(length < short_segment_mm for length in segments)
    very_short = sum(length < very_short_segment_mm for length in segments)
    ratio = short / len(segments) if segments else 0.0
    risk = "low" if ratio < 0.10 else "medium" if ratio <= 0.30 else "high"
    p95 = 0.0
    if segments:
        ordered = sorted(segments)
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    total = draw_time + travel_time + z_time + dwell
    return {
        "profile": profile.name,
        "stroke_count": count,
        "point_count": sum(len(stroke.points) for stroke in strokes),
        "xy_draw_commands": len(segments),
        "xy_travel_commands": count,
        "pen_down_count": count,
        "pen_up_count": count + 1,
        "pen_lift_count": count,
        "pen_lift_distance_mm": round(count * z_one_way, 6),
        "pen_lower_distance_mm": round(count * z_one_way, 6),
        "total_z_distance_mm": round(z_distance, 6),
        "draw_distance_mm": round(draw, 6),
        "travel_distance_mm": round(travel, 6),
        "dwell_count": dwell_count,
        "dwell_time_seconds": round(dwell, 6),
        "ideal_draw_time_seconds": round(draw_time, 6),
        "ideal_travel_time_seconds": round(travel_time, 6),
        "ideal_z_time_seconds": round(z_time, 6),
        "ideal_total_time_seconds": round(total, 6),
        "ideal_total_time_minutes": round(total / 60, 6),
        "short_segment_count": short,
        "very_short_segment_count": very_short,
        "short_segment_ratio": round(ratio, 6),
        "average_segment_length_mm": round(statistics.fmean(segments), 6) if segments else 0,
        "median_segment_length_mm": round(statistics.median(segments), 6) if segments else 0,
        "p95_segment_length_mm": round(p95, 6),
        "planner_risk": risk,
        "gcode_command_count": 0,
        "draw_feed_mm_min": profile.feedrate.draw_mm_min,
        "travel_feed_mm_min": profile.feedrate.travel_mm_min,
        "z_feed_mm_min": profile.feedrate.z_mm_min,
        "up_z_mm": profile.pen.up_z_mm,
        "down_z_mm": profile.pen.down_z_mm,
        "down_settle_ms": profile.pen.down_settle_ms,
    }
