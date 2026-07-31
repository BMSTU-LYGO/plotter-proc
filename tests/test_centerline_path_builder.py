from pathlib import Path

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CenterlineStroke,
    CompiledCenterlineFont,
)
from plotter_processor.centerline_path_builder import build_centerline_paths
from plotter_processor.models import PageSpec, Point, PositionedGlyph


def test_builds_page_paths_from_font_units() -> None:
    glyph = CenterlineGlyph(
        "А",
        ord("А"),
        "uni0410",
        600,
        (CenterlineStroke(0, (Point(0, 0), Point(100, 200)), False),),
    )
    font = CompiledCenterlineFont(
        Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {"А": glyph}
    )
    positioned = PositionedGlyph("А", ord("А"), "uni0410", 10, 20, 3, 0.005, 0, 0)
    paths = build_centerline_paths(font, [positioned], PageSpec("A5", 148, 210))
    assert paths.strokes[0].points == [Point(10, 20), Point(10.5, 19)]
    assert paths.metadata["pipeline"] == "ttf-centerline"
