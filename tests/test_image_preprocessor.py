from pathlib import Path

from PIL import Image, ImageDraw

from plotter_processor.image_preprocessor import preprocess_image


def _options() -> dict[str, object]:
    return {
        "max_input_pixels": 100000,
        "max_working_side_px": 64,
        "autocontrast": True,
        "blur_sigma": 0.0,
        "threshold": {"method": "otsu", "value": 160},
        "remove_small_objects_px": 1,
    }


def test_transparent_png_is_composited_on_white_and_resized(tmp_path: Path) -> None:
    source = tmp_path / "transparent.png"
    image = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(image).line((10, 10, 180, 80), fill=(0, 0, 0, 255), width=5)
    image.save(source)

    result = preprocess_image(source, _options(), debug_path=tmp_path / "debug.png")

    assert max(result.working_size) == 64
    assert result.grayscale[0, 0] > 0.95
    assert (tmp_path / "debug.png").is_file()


def test_input_pixel_limit_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "large.png"
    Image.new("RGB", (400, 400), "white").save(source)

    try:
        preprocess_image(source, _options())
    except ValueError as error:
        assert "max_input_pixels" in str(error)
    else:
        raise AssertionError("pixel limit was not enforced")
