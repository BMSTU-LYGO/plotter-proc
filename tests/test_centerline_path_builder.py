from pathlib import Path

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CenterlineStroke,
    CompiledCenterlineFont,
    compiled_glyph_metadata,
)
from plotter_processor.centerline_path_builder import (
    CenterlinePathTemplateCache,
    build_centerline_paths,
)
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


def test_reuses_scaled_local_template_across_translated_glyphs() -> None:
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
    positioned = [
        PositionedGlyph("А", ord("А"), "uni0410", x, 20, 3, 0.005, 0, index)
        for index, x in enumerate((10, 30))
    ]
    cache = CenterlinePathTemplateCache()

    paths = build_centerline_paths(
        font, positioned, PageSpec("A5", 148, 210), template_cache=cache
    )

    assert paths.strokes[0].points == [Point(10, 20), Point(10.5, 19)]
    assert paths.strokes[1].points == [Point(30, 20), Point(30.5, 19)]
    assert cache.snapshot() == {
        "build_template_cache_hits": 1,
        "build_template_cache_misses": 1,
        "build_local_points_built": 2,
        "build_output_points_allocated": 4,
        "build_positioned_template_hits": 0,
        "build_positioned_template_misses": 2,
    }


def test_scale_is_part_of_local_template_cache_key() -> None:
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
    cache = CenterlinePathTemplateCache()
    for index, scale in enumerate((0.005, 0.01)):
        positioned = PositionedGlyph(
            "А", ord("А"), "uni0410", 10, 20, 3, scale, 0, index
        )
        build_centerline_paths(
            font, [positioned], PageSpec("A5", 148, 210), template_cache=cache
        )

    assert cache.template_cache_misses == 2
    assert cache.template_cache_hits == 0


def test_reuses_immutable_points_for_identically_positioned_glyphs() -> None:
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
    cache = CenterlinePathTemplateCache()
    results = []
    for glyph_index in (0, 1):
        positioned = PositionedGlyph(
            "А", ord("А"), "uni0410", 10, 20, 3, 0.005, 0, glyph_index
        )
        results.append(
            build_centerline_paths(
                font,
                [positioned],
                PageSpec("A5", 148, 210),
                template_cache=cache,
            )
        )

    assert cache.positioned_template_hits == 1
    assert cache.positioned_template_misses == 1
    assert results[0].strokes[0].points is not results[1].strokes[0].points
    assert results[0].strokes[0].points[0] is results[1].strokes[0].points[0]


def test_materializes_recommended_cyrillic_stroke_order_and_direction() -> None:
    right = CenterlineStroke(5, (Point(20, 0), Point(10, 0)), False)
    left = CenterlineStroke(2, (Point(0, 0), Point(5, -10)), False)
    entry, exit_anchor, metadata = compiled_glyph_metadata((right, left), char="ы")
    glyph = CenterlineGlyph(
        "ы",
        ord("ы"),
        "uni044B",
        600,
        (right, left),
        entry_anchor=entry,
        exit_anchor=exit_anchor,
        stroke_metadata=metadata,
    )
    font = CompiledCenterlineFont(
        Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {"ы": glyph}
    )
    positioned = PositionedGlyph("ы", ord("ы"), "uni044B", 10, 20, 3, 0.01, 0, 0)

    paths = build_centerline_paths(font, [positioned], PageSpec("A5", 148, 210))

    assert [stroke.contour_index for stroke in paths.strokes] == [2, 5]
    assert paths.strokes[0].points == [Point(10, 20), Point(10.05, 20.1)]
    assert paths.strokes[1].points == [Point(10.1, 20), Point(10.2, 20)]
