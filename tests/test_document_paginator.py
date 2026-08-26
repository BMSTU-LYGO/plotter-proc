from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from plotter_processor.document_models import (
    SourceDocument,
    SourceLineElement,
    SourcePage,
    SourcePoint,
    SourceRasterImageElement,
    SourceTextElement,
)
from plotter_processor.document_paginator import paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec
from plotter_processor.page_layout_model import LayoutModel, LayoutPage


def _config() -> dict[str, object]:
    return yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))


def _paginate(text: str, test_font: Path, *, height: float = 55.0):
    config = _config()
    document = SourceDocument(
        Path("input.txt"),
        (SourcePage(0, None, None, (SourceTextElement("text-1", 0, 0, (text,)),)),),
    )
    with load_font(test_font) as font:
        return paginate_document(
            document, font, PageSpec("test", 80, height), config["margins_mm"],
            config["sizes"]["normal"], config["images"], config["pagination"],
            preserve_source_page_breaks=False,
        )


def test_short_document_is_one_page_and_long_document_is_stable(test_font: Path) -> None:
    short = _paginate("Short text", test_font)
    assert isinstance(short, LayoutModel)
    assert isinstance(short.pages[0], LayoutPage)
    assert len(short.pages) == 1
    text = " ".join(f"word{index}" for index in range(120))

    first = _paginate(text, test_font)
    second = _paginate(text, test_font)

    assert len(first.pages) > 1
    assert len(first.pages) == len(second.pages)
    assert [len(page.layout.glyphs) for page in first.pages] == [
        len(page.layout.glyphs) for page in second.pages
    ]
    expected = "".join(text.split())
    actual = "".join(glyph.char for page in first.pages for glyph in page.layout.glyphs)
    assert actual == expected
    assert all(page.layout.glyphs for page in first.pages)


def test_long_word_is_split_and_warned(test_font: Path) -> None:
    result = _paginate("A" * 200, test_font)

    assert len(result.pages) > 1
    assert any("forced_word_break" in page.warnings for page in result.pages)
    assert sum(len(page.layout.glyphs) for page in result.pages) == 200


def test_image_moves_whole_to_next_page_and_stays_above_footer(
    tmp_path: Path, test_font: Path
) -> None:
    config = _config()
    image_path = tmp_path / "line.png"
    image = Image.new("RGB", (100, 50), "white")
    ImageDraw.Draw(image).line((5, 5, 95, 45), fill="black", width=4)
    image.save(image_path)
    document = SourceDocument(
        tmp_path / "mixed.docx",
        (
            SourcePage(
                0,
                None,
                None,
                (
                    SourceTextElement("text", 0, 0, ("\n".join(["Line"] * 5),)),
                    SourceRasterImageElement(
                        "image", 1, 0, image_path, 100, 50, 50.0, 25.0
                    ),
                ),
            ),
        ),
    )
    page = PageSpec("test", 80, 70)
    with load_font(test_font) as font:
        result = paginate_document(
            document, font, page, config["margins_mm"], config["sizes"]["normal"],
            config["images"], config["pagination"], preserve_source_page_breaks=False,
        )

    image_pages = [page for page in result.pages if "image" in page.source_element_ids]
    assert len(image_pages) == 1
    image_page = image_pages[0]
    assert image_page.graphic_strokes
    footer_top = page.height_mm - config["margins_mm"]["bottom"] - 8.0
    assert max(point.y for stroke in image_page.graphic_strokes for point in stroke.points) < footer_top


def test_a4_semantic_line_is_scaled_into_a5_page(test_font: Path) -> None:
    config = _config()
    line = SourceLineElement(
        "page-001-line-001",
        0,
        0,
        SourcePoint(10.0, 36.0),
        SourcePoint(200.0, 36.0),
        semantic_role="underline",
    )
    document = SourceDocument(
        Path("input.pdf"),
        (SourcePage(0, 595.2756, 841.8898, (line,)),),
    )
    page = PageSpec("A5", 148.0, 210.0)

    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            page,
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            document_layout_mode="preserve",
        )

    stroke = result.pages[0].graphic_strokes[0]
    assert max(point.x for point in stroke.points) <= page.width_mm
    assert stroke.points[1].x - stroke.points[0].x < 190.0


@pytest.mark.parametrize(
    "page",
    [PageSpec("A5", 148.0, 210.0), PageSpec("A4", 210.0, 297.0)],
)
def test_display_math_is_centered_with_spacing_on_standard_pages(
    page: PageSpec, test_font: Path
) -> None:
    config = _config()
    document = SourceDocument(
        Path("display.txt"),
        (SourcePage(0, None, None, (
            SourceTextElement("display", 0, 0, (r"$$\frac{x+1}{x-1}$$",)),
        )),),
    )
    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            page,
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            latex_mode="mathtext",
            latex_options=config["latex"],
            preserve_source_page_breaks=False,
        )

    formula = result.pages[0].metadata["formulas"][0]
    target = formula["target_bbox"]
    content_center = (
        config["margins_mm"]["left"]
        + page.width_mm
        - config["margins_mm"]["right"]
    ) / 2
    assert target["x"] + target["width"] / 2 == pytest.approx(content_center, abs=0.2)
    assert result.pages[0].layout.used_height_mm >= (
        target["height"]
        + config["latex"]["block_spacing_before_mm"]
        + config["latex"]["block_spacing_after_mm"]
    )


def test_display_math_moves_whole_to_next_page(test_font: Path) -> None:
    config = _config()
    document = SourceDocument(
        Path("display-break.txt"),
        (SourcePage(0, None, None, (
            SourceTextElement(
                "display-break",
                0,
                0,
                ("Line one", "Line two", "Line three", r"$$\frac{x+1}{x-1}$$"),
            ),
        )),),
    )
    with load_font(test_font) as font:
        result = paginate_document(
            document,
            font,
            PageSpec("small", 80.0, 55.0),
            config["margins_mm"],
            config["sizes"]["normal"],
            config["images"],
            config["pagination"],
            latex_mode="mathtext",
            latex_options=config["latex"],
            preserve_source_page_breaks=False,
        )

    formula_pages = [
        page for page in result.pages if page.metadata["formulas"]
    ]
    assert len(formula_pages) == 1
    assert formula_pages[0].page_index > 0
    formula_id = formula_pages[0].metadata["formulas"][0]["element_id"]
    assert all(
        stroke.element_id == formula_id for stroke in formula_pages[0].graphic_strokes
    )
