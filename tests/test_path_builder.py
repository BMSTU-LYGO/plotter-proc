from pathlib import Path

from plotter_processor.config import load_yaml
from plotter_processor.font_loader import load_font
from plotter_processor.models import (
    PageSpec,
    PathDocument,
    PlotterStroke,
    Point,
    PositionedGlyph,
)
from plotter_processor.path_builder import (
    OutlinePathTemplateCache,
    build_paths,
    load_path_document,
    save_path_document,
)


def test_paths_v2_round_trip(tmp_path: Path) -> None:
    source = PathDocument(
        148,
        210,
        [PlotterStroke(0, [Point(1, 2), Point(3, 4)], False, 2, "ё", 1)],
        ["warning"],
        {"pipeline": "ttf-vector"},
    )
    path = tmp_path / "paths.json"
    save_path_document(source, path)
    loaded = load_path_document(path)
    assert loaded == source
    assert "dpi" not in path.read_text(encoding="utf-8")


def test_extracted_asset_provenance_is_byte_stable_between_output_directories(
    tmp_path: Path,
) -> None:
    outputs = []
    for job_name in ("output-A", "output-B"):
        document = PathDocument(
            148,
            210,
            [
                PlotterStroke(
                    0,
                    [Point(1, 2), Point(3, 4)],
                    False,
                    element_id="page-001-image-001",
                    element_type="raster-image",
                    source_path=str(
                        tmp_path
                        / job_name
                        / "extracted-assets"
                        / "image-001-deadbeef.png"
                    ),
                )
            ],
            [],
        )
        target = tmp_path / job_name / "paths.json"
        save_path_document(document, target)
        outputs.append(target.read_bytes())

    assert outputs[0] == outputs[1]
    assert b"asset://image-001-deadbeef.png" in outputs[0]


def test_outline_builder_reuses_flattened_glyph_template() -> None:
    cache = OutlinePathTemplateCache()
    vector = load_yaml(Path("configs/layout.yaml"))["vector"]
    with load_font(Path("assets/1.ttf")) as font:
        glyph_name = font.glyph_name_for_char("A")
        glyphs = [
            PositionedGlyph(
                "A", ord("A"), glyph_name, x, 20, 3, 0.005, 0, index
            )
            for index, x in enumerate((10.0, 30.0))
        ]
        paths = build_paths(
            font,
            glyphs,
            PageSpec("A5", 148, 210),
            vector,
            template_cache=cache,
        )

    assert cache.template_cache_misses == 1
    assert cache.template_cache_hits == 1
    assert cache.output_points_allocated == cache.local_points_built * 2
    first = [stroke for stroke in paths.strokes if stroke.glyph_index == 0]
    second = [stroke for stroke in paths.strokes if stroke.glyph_index == 1]
    assert len(first) == len(second)
    assert all(
        right.points[0].x - left.points[0].x == 20.0
        and right.points[0].y == left.points[0].y
        for left, right in zip(first, second, strict=True)
    )
