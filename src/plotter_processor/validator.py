import math
from pathlib import Path

from PIL import ImageFont

from plotter_processor.models import PathDocument

FONT_TEST_TEXT = "АБВГД абвгд 0123456789"


def validate_font(font_path: str | Path, size: int = 36) -> None:
    path = Path(font_path)
    if not path.is_file():
        raise FileNotFoundError(f"Font file does not exist: {path}")
    try:
        font = ImageFont.truetype(str(path), size=size)
    except OSError as error:
        raise ValueError(f"Pillow cannot open font: {path}") from error

    if font.getbbox(FONT_TEST_TEXT) is None or not bytes(font.getmask(FONT_TEST_TEXT)):
        raise ValueError("Font test string rendered empty")

    glyphs = {bytes(font.getmask(character)) for character in "АБВГДабвгд"}
    if len(glyphs) < 3:
        raise ValueError("Font does not appear to contain Cyrillic glyphs")


def path_statistics(document: PathDocument) -> dict[str, float | int]:
    draw_distance = 0.0
    travel_distance = 0.0
    points = 0
    previous_end = None

    for stroke in document.strokes:
        points += len(stroke.points)
        for first, second in zip(stroke.points, stroke.points[1:], strict=False):
            draw_distance += math.hypot(second.x - first.x, second.y - first.y)
        if previous_end is not None:
            start = stroke.points[0]
            travel_distance += math.hypot(start.x - previous_end.x, start.y - previous_end.y)
        previous_end = stroke.points[-1]

    if draw_distance <= 0:
        raise ValueError("Total drawing path length is zero")
    return {
        "strokes": len(document.strokes),
        "points": points,
        "draw_distance_mm": round(draw_distance, 3),
        "travel_distance_mm": round(travel_distance, 3),
    }
