from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.path_builder import path_statistics
from plotter_processor.path_optimizer import optimize_paths


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
