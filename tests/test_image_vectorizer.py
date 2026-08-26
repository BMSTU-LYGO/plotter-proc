from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from plotter_processor.image_preprocessor import preprocess_image
from plotter_processor.image_vectorizer import vectorize_image


def _options() -> dict[str, object]:
    return {
        "max_input_pixels": 100000,
        "max_working_side_px": 128,
        "autocontrast": True,
        "blur_sigma": 0.0,
        "threshold": {"method": "otsu"},
        "remove_small_objects_px": 1,
        "edge": {"sigma": 1.0, "low_threshold": 0.08, "high_threshold": 0.2},
        "vector": {
            "simplify_tolerance_mm": 0.05,
            "min_stroke_length_mm": 0.1,
            "max_points_per_image": 10000,
            "max_strokes_per_image": 1000,
        },
    }


def test_outline_centerline_and_hatching_create_bounded_distinct_strokes(tmp_path: Path) -> None:
    source = tmp_path / "line.png"
    image = Image.new("RGB", (80, 50), "white")
    ImageDraw.Draw(image).line((5, 5, 70, 40), fill="black", width=4)
    image.save(source)
    prepared = preprocess_image(source, _options())

    outline = vectorize_image(prepared, _options(), mode="outline", width_mm=40, height_mm=25)
    centerline = vectorize_image(
        prepared, _options(), mode="centerline", width_mm=40, height_mm=25
    )
    hatching = vectorize_image(
        prepared, _options(), mode="hatching", width_mm=40, height_mm=25
    )

    assert outline.strokes and centerline.strokes and hatching.strokes
    assert all(
        0 <= point.x <= 40 and 0 <= point.y <= 25
        for result in (outline, centerline, hatching)
        for stroke in result.strokes
        for point in stroke.points
    )
    assert hatching.mode == "hatching"
    assert all(stroke.segment_types == ("image-hatching",) for stroke in hatching.strokes)
    assert len({len(result.strokes) for result in (outline, centerline, hatching)}) >= 2
    assert isinstance(outline.micro_strokes_suppressed, int)
    assert isinstance(centerline.micro_strokes_suppressed, int)


def test_hatching_density_tracks_darkness_and_obeys_path_limit(tmp_path: Path) -> None:
    source = tmp_path / "tones.png"
    image = Image.new("L", (100, 60), 220)
    ImageDraw.Draw(image).rectangle((0, 0, 49, 59), fill=35)
    image.save(source)
    options = _options()
    options["hatching"] = {
        "spacing_mm": 1.0,
        "levels": 4,
        "min_feature_size_mm": 0.2,
    }
    prepared = preprocess_image(source, options)

    result = vectorize_image(
        prepared,
        options,
        mode="hatching",
        width_mm=50,
        height_mm=30,
    )
    dark_length = sum(
        stroke.points[-1].x - stroke.points[0].x
        for stroke in result.strokes
        if stroke.points[0].x < 25
    )
    light_length = sum(
        stroke.points[-1].x - stroke.points[0].x
        for stroke in result.strokes
        if stroke.points[0].x >= 25
    )
    assert dark_length > light_length

    limited = _options()
    limited["hatching"] = options["hatching"]
    limited["vector"]["max_strokes_per_image"] = 1
    with pytest.raises(ValueError, match="complexity limits"):
        vectorize_image(
            prepared,
            limited,
            mode="hatching",
            width_mm=50,
            height_mm=30,
        )
