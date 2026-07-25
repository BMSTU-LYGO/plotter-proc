from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage import measure

from plotter_processor.models import RenderedPage

PAGE_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
}
OVERFLOW_ERROR = (
    "Text does not fit on one page with selected size. "
    "Choose a smaller size or split the document."
)
DISCONNECTED_FONT_WARNING = (
    "Selected font does not appear to be connected. Use a connected handwriting font."
)


def mm_to_px(value_mm: float, dpi: int) -> int:
    return round(value_mm * dpi / 25.4)


def render_page(
    paragraphs: list[str],
    font_path: str | Path,
    page: str,
    size: str,
    layout_config: dict[str, Any],
) -> RenderedPage:
    if page not in PAGE_SIZES_MM:
        raise ValueError(f"Unsupported page size: {page}")

    dpi = _positive_int(layout_config.get("dpi"), "dpi")
    size_options = layout_config.get("sizes", {}).get(size)
    if not isinstance(size_options, dict):
        raise TypeError(f"Unsupported text size: {size}")

    margins = layout_config.get("margins_mm")
    if not isinstance(margins, dict):
        raise TypeError("Layout configuration is missing margins_mm")

    page_width_mm, page_height_mm = PAGE_SIZES_MM[page]
    width_px = mm_to_px(page_width_mm, dpi)
    height_px = mm_to_px(page_height_mm, dpi)
    left = mm_to_px(_nonnegative_float(margins.get("left"), "left margin"), dpi)
    right = width_px - mm_to_px(_nonnegative_float(margins.get("right"), "right margin"), dpi)
    top = mm_to_px(_nonnegative_float(margins.get("top"), "top margin"), dpi)
    bottom = height_px - mm_to_px(
        _nonnegative_float(margins.get("bottom"), "bottom margin"), dpi
    )
    if left >= right or top >= bottom:
        raise ValueError("Page margins leave no usable drawing area")

    font_size = _positive_int(size_options.get("font_px"), f"{size}.font_px")
    line_spacing = _positive_float(size_options.get("line_spacing"), f"{size}.line_spacing")
    paragraph_spacing = _nonnegative_float(
        size_options.get("paragraph_spacing_lines"), f"{size}.paragraph_spacing_lines"
    )
    font = _load_font(font_path, font_size)
    line_height = max(1, round(font_size * line_spacing))
    paragraph_gap = round(line_height * paragraph_spacing)

    image = Image.new("L", (width_px, height_px), color=255)
    draw = ImageDraw.Draw(image)
    cursor_y = top
    line_boxes: list[tuple[int, int, int, int]] = []
    rendered_lines: list[str] = []

    for paragraph_index, paragraph in enumerate(paragraphs):
        lines = _wrap_paragraph(paragraph, font, right - left)
        if not lines:
            cursor_y += line_height
            if cursor_y > bottom:
                raise ValueError(OVERFLOW_ERROR)
        else:
            for line in lines:
                box = draw.textbbox((left, cursor_y), line, font=font)
                if box[2] > right or box[3] > bottom:
                    raise ValueError(OVERFLOW_ERROR)
                draw.text((left, cursor_y), line, font=font, fill=0)
                line_boxes.append(box)
                rendered_lines.append(line)
                cursor_y += line_height

        if paragraph_index < len(paragraphs) - 1 and paragraph:
            cursor_y += paragraph_gap
            if cursor_y > bottom:
                raise ValueError(OVERFLOW_ERROR)

    image_array = np.asarray(image, dtype=np.uint8).copy()
    warnings: list[str] = []
    if _appears_disconnected(image_array, rendered_lines):
        warnings.append(DISCONNECTED_FONT_WARNING)

    return RenderedPage(
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
        image=image_array,
        line_boxes=line_boxes,
        warnings=warnings,
    )


def save_rendered_page(page: RenderedPage, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(page.image, mode="L").save(path)


def _wrap_paragraph(paragraph: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = paragraph.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    if _text_width(current, font) > max_width:
        raise ValueError(OVERFLOW_ERROR)

    for word in words[1:]:
        if _text_width(word, font) > max_width:
            raise ValueError(OVERFLOW_ERROR)
        candidate = f"{current} {word}"
        if _text_width(candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _load_font(path: str | Path, size: int) -> ImageFont.FreeTypeFont:
    font_path = Path(path)
    if not font_path.is_file():
        raise FileNotFoundError(f"Font file does not exist: {font_path}")
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError as error:
        raise ValueError(f"Pillow cannot open font: {font_path}") from error


def _appears_disconnected(image: np.ndarray, lines: list[str]) -> bool:
    character_count = sum(character.isalnum() for line in lines[:3] for character in line)
    if character_count < 10:
        return False
    labels = measure.label(image < 128, connectivity=2)
    component_count = int(labels.max())
    return component_count >= character_count * 0.8


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _nonnegative_float(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be non-negative")
    return float(value)
