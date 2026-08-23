from pathlib import Path

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


def test_outline_and_centerline_create_bounded_strokes(tmp_path: Path) -> None:
    source = tmp_path / "line.png"
    image = Image.new("RGB", (80, 50), "white")
    ImageDraw.Draw(image).line((5, 5, 70, 40), fill="black", width=4)
    image.save(source)
    prepared = preprocess_image(source, _options())

    outline = vectorize_image(prepared, _options(), mode="outline", width_mm=40, height_mm=25)
    centerline = vectorize_image(
        prepared, _options(), mode="centerline", width_mm=40, height_mm=25
    )

    assert outline.strokes and centerline.strokes
    assert all(0 <= point.x <= 40 and 0 <= point.y <= 25 for s in centerline.strokes for point in s.points)
    assert isinstance(outline.micro_strokes_suppressed, int)
    assert isinstance(centerline.micro_strokes_suppressed, int)
