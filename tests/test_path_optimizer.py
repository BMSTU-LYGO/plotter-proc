from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.path_builder import path_statistics
from plotter_processor.path_optimizer import (
    RetraceConfig,
    load_retrace_config,
    optimize_paths,
    optimize_word_strokes,
)


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


def test_superfast_costs_make_short_retrace_cheaper_than_pen_lift() -> None:
    config = load_retrace_config(
        {
            "enabled": True,
            "max_length_mm": 1.2,
            "max_repeats": 1,
            "allowed_segment_types": ["glyph"],
            "profiles": {
                "superfast": {"max_length_mm": 3.0, "max_repeats": 3}
            },
        },
        mode="superfast",
        routing_values={
            "cost": {},
            "cost_profiles": {
                "superfast": {"pen_lift": 24.0, "retrace": 0.65}
            },
        },
    )

    assert config.mode == "superfast"
    assert config.max_length_mm == 3.0
    assert config.weights.pen_lift > config.weights.retrace * config.max_length_mm


def test_superfast_routes_each_cyrillic_glyph_as_endpoint_graph() -> None:
    zhe_trunk = PlotterStroke(
        0,
        [Point(0, 0), Point(1, 0), Point(2, 0)],
        False,
        0,
        char="ж",
        segment_types=("glyph",),
        element_id="text:0",
    )
    zhe_branch = PlotterStroke(
        1,
        [Point(1, 0), Point(1, 1)],
        False,
        0,
        char="ж",
        segment_types=("glyph",),
        element_id="text:0",
    )
    em = PlotterStroke(
        2,
        [Point(10, 0), Point(11, 0)],
        False,
        1,
        char="м",
        segment_types=("glyph",),
        element_id="text:0",
    )
    config = RetraceConfig(
        max_length_mm=3.0,
        max_repeats=3,
        mode="superfast",
        max_retrace_ratio=0.65,
    )

    optimized = optimize_paths(
        PathDocument(100, 100, [zhe_trunk, zhe_branch, em], []), config
    )

    assert len(optimized.strokes) == 2
    assert optimized.strokes[0].char == "ж"
    assert optimized.strokes[0].points[-1] == Point(1, 1)
    assert optimized.metadata["safe_retrace"]["retrace_pen_lifts_saved"] == 1


def test_superfast_routes_a_whole_word_and_reverses_secondary_strokes() -> None:
    main = PlotterStroke(
        0,
        [Point(0, 0), Point(1, 0), Point(2, 0)],
        False,
        0,
        char="мир",
        segment_types=("glyph", "connector", "glyph"),
        word_index=4,
    )
    secondary = PlotterStroke(
        1,
        [Point(1, 1), Point(1, 0)],
        False,
        1,
        char="и",
        segment_types=("glyph",),
        word_index=4,
    )
    config = RetraceConfig(
        max_length_mm=3.0,
        max_repeats=3,
        allowed_segment_types=frozenset({"glyph", "connector"}),
        mode="superfast",
        max_retrace_ratio=0.65,
    )

    optimized, report = optimize_word_strokes([main, secondary], config)

    assert len(optimized) == 1
    assert optimized[0].points[-1] == Point(1, 1)
    assert report["continuous_passes"] == 1
    assert report["retrace_pen_lifts_saved"] == 1
