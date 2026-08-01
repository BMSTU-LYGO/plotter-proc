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
