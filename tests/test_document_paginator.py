from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from plotter_processor.document_models import (
    SourceDocument,
    SourcePage,
    SourceRasterImageElement,
    SourceTextElement,
)
from plotter_processor.document_paginator import paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec


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
    assert len(_paginate("Short text", test_font).pages) == 1
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
