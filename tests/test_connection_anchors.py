from plotter_processor.centerline_font.anchors import entry_exit_anchors
from plotter_processor.centerline_font.stroke_roles import classify_strokes
from plotter_processor.models import PlotterStroke, Point


def test_roles_keep_diacritic_secondary() -> None:
    body = PlotterStroke(0, [Point(0, 10), Point(4, 10)], False)
    dot = PlotterStroke(1, [Point(2, 7), Point(2.1, 7)], False)
    result = classify_strokes([body, dot], 10)
    assert result.main is body
    assert result.diacritics == (dot,)


def test_anchor_selection_is_stable_left_to_right() -> None:
    stroke = PlotterStroke(3, [Point(1, 10), Point(2, 9), Point(4, 10)], False)
    entry, exit = entry_exit_anchors(stroke, 10) or (None, None)
    assert entry is not None and entry.side == "left"
    assert exit is not None and exit.side == "right"
    assert entry.point.x < exit.point.x
    assert entry.kind == exit.kind == "terminal"
    assert entry.connectable and exit.connectable


def test_anchor_tangent_uses_local_terminal_geometry() -> None:
    stroke = PlotterStroke(
        4,
        [Point(0, 10), Point(0.2, 9.8), Point(1.5, 8), Point(4, 10)],
        False,
    )

    entry, exit = entry_exit_anchors(stroke, 10) or (None, None)

    assert entry is not None and exit is not None
    assert entry.tangent.x > 0
    assert entry.tangent.y < 0
    assert exit.tangent.x > 0
    assert exit.confidence == 1.0


def test_non_routeable_terminal_is_marked_for_safe_fallback() -> None:
    stroke = PlotterStroke(
        5,
        [Point(0, 10), Point(1, 9), Point(-1, 10)],
        False,
    )

    entry, exit = entry_exit_anchors(stroke, 10) or (None, None)

    assert entry is not None and exit is not None
    assert not (entry.connectable and exit.connectable)
    assert min(entry.confidence, exit.confidence) == 0.25
