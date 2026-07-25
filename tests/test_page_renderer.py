from pathlib import Path

import numpy as np
import pytest

from plotter_processor.config import load_yaml
from plotter_processor.page_renderer import OVERFLOW_ERROR, mm_to_px, render_page

FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
CONFIG_PATH = Path("configs/layout.yaml")


@pytest.fixture
def layout_config() -> dict[str, object]:
    return load_yaml(CONFIG_PATH)


def require_test_font() -> Path:
    if not FONT_PATH.is_file():
        pytest.skip("System test font is unavailable")
    return FONT_PATH


def test_renders_a4_at_configured_dpi(layout_config: dict[str, object]) -> None:
    rendered = render_page(
        ["Привет, мир!"], require_test_font(), "A4", "normal", layout_config
    )

    assert rendered.width_px == mm_to_px(210.0, 200)
    assert rendered.height_px == mm_to_px(297.0, 200)
    assert rendered.image.shape == (rendered.height_px, rendered.width_px)
    assert rendered.image.dtype == np.uint8
    assert np.any(rendered.image < 255)


def test_rendered_ink_stays_inside_margins(layout_config: dict[str, object]) -> None:
    rendered = render_page(
        ["Длинная строка текста " * 12], require_test_font(), "A5", "small", layout_config
    )
    ink_y, ink_x = np.where(rendered.image < 255)

    assert ink_x.min() >= mm_to_px(10.0, rendered.dpi)
    assert ink_x.max() < rendered.width_px - mm_to_px(10.0, rendered.dpi)
    assert ink_y.min() >= mm_to_px(20.0, rendered.dpi)
    assert ink_y.max() < rendered.height_px - mm_to_px(30.0, rendered.dpi)


def test_wraps_text_to_multiple_lines(layout_config: dict[str, object]) -> None:
    rendered = render_page(
        ["слово " * 40], require_test_font(), "A5", "normal", layout_config
    )

    assert len(rendered.line_boxes) > 1


def test_empty_paragraph_adds_vertical_space(layout_config: dict[str, object]) -> None:
    without_empty = render_page(
        ["Первая", "Вторая"], require_test_font(), "A4", "normal", layout_config
    )
    with_empty = render_page(
        ["Первая", "", "Вторая"], require_test_font(), "A4", "normal", layout_config
    )

    assert with_empty.line_boxes[-1][1] > without_empty.line_boxes[-1][1]


def test_reports_page_overflow(layout_config: dict[str, object]) -> None:
    paragraphs = ["Строка текста " * 20] * 100

    with pytest.raises(ValueError, match="does not fit"):
        render_page(paragraphs, require_test_font(), "A5", "large", layout_config)

    assert OVERFLOW_ERROR.startswith("Text does not fit")


def test_rejects_word_wider_than_page(layout_config: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="does not fit"):
        render_page(["А" * 500], require_test_font(), "A5", "large", layout_config)
