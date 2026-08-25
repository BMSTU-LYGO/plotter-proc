from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.path_builder import path_statistics
from plotter_processor.path_optimizer import RetraceConfig, optimize_paths


def test_optimizer_preserves_draw_distance_and_reduces_travel() -> None:
    document = PathDocument(
        100,
        100,
        [
            PlotterStroke(0, [Point(0, 0), Point(1, 0)], False, 0),
            PlotterStroke(1, [Point(20, 0), Point(21, 0)], False, 0),
            PlotterStroke(2, [Point(3, 0), Point(2, 0)], False, 0),
        ],
        [],
    )
    before = path_statistics(document)
    after = path_statistics(optimize_paths(document))
    assert after["draw_distance_mm"] == before["draw_distance_mm"]
    assert after["travel_distance_mm"] <= before["travel_distance_mm"]


def test_optimizer_never_splits_or_reorders_points_inside_euler_route() -> None:
    route = PlotterStroke(
        0,
        [Point(0, 0), Point(2, 0), Point(1, 0), Point(3, 0)],
        False,
        0,
    )
    optimized = optimize_paths(PathDocument(100, 100, [route], [], {"pipeline": "ttf-centerline"}))
    assert len(optimized.strokes) == 1
    assert optimized.strokes[0].points in [route.points, list(reversed(route.points))]


def test_next_glyph_context_selects_equivalent_exit_without_large_detour() -> None:
    current = PlotterStroke(
        0,
        [Point(0, 0), Point(1, 0)],
        False,
        0,
    )
    following = PlotterStroke(
        1,
        [Point(1.1, 0), Point(2, 0)],
        False,
        1,
    )
    document = PathDocument(100, 100, [current, following], [])

    optimized = optimize_paths(document)

    assert optimized.strokes[0].points[-1] == Point(1, 0)
    assert optimized.strokes[1].points[0] == Point(1.1, 0)


def test_explicit_stroke_order_is_not_rebuilt_for_next_glyph() -> None:
    ordered = [
        PlotterStroke(
            0,
            [Point(5, 0), Point(6, 0)],
            False,
            0,
            preserve_order=True,
        ),
        PlotterStroke(
            1,
            [Point(0, 0), Point(1, 0)],
            False,
            0,
            preserve_order=True,
        ),
    ]
    following = PlotterStroke(2, [Point(1.1, 0), Point(2, 0)], False, 1)

    optimized = optimize_paths(PathDocument(100, 100, [*ordered, following], []))

    assert [stroke.points for stroke in optimized.strokes[:2]] == [
        stroke.points for stroke in ordered
    ]


def test_safe_short_retrace_saves_one_pen_lift() -> None:
    trunk = PlotterStroke(
        0,
        [Point(0, 0), Point(1, 0), Point(2, 0)],
        False,
        0,
        segment_types=("glyph",),
    )
    branch = PlotterStroke(
        1,
        [Point(1, 0), Point(1, 1)],
        False,
        0,
        segment_types=("glyph",),
    )

    optimized = optimize_paths(PathDocument(100, 100, [trunk, branch], []))

    assert len(optimized.strokes) == 1
    assert optimized.strokes[0].points == [
        Point(0, 0),
        Point(1, 0),
        Point(2, 0),
        Point(1, 0),
        Point(1, 1),
    ]
    assert "retrace" in optimized.strokes[0].segment_types
    assert optimized.metadata["safe_retrace"] == {
        "retrace_enabled": True,
        "retrace_merges": 1,
        "retrace_pen_lifts_saved": 1,
        "retrace_distance_mm": 1.0,
    }


def test_retrace_rejects_long_or_non_glyph_repetition() -> None:
    trunk = PlotterStroke(
        0,
        [Point(0, 0), Point(2, 0), Point(4, 0)],
        False,
        0,
        segment_types=("glyph",),
    )
    long_branch = PlotterStroke(
        1,
        [Point(2, 0), Point(2, 1)],
        False,
        0,
        segment_types=("glyph",),
    )
    connector = PlotterStroke(
        2,
        [Point(4, 0), Point(4, 1)],
        False,
        0,
        segment_types=("connector",),
    )

    optimized = optimize_paths(
        PathDocument(100, 100, [trunk, long_branch, connector], []),
        RetraceConfig(max_length_mm=1.2),
    )

    assert len(optimized.strokes) == 3
    assert optimized.metadata["safe_retrace"]["retrace_merges"] == 0
