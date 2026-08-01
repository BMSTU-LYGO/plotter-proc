from pathlib import Path

import pytest
import yaml

from plotter_processor.document_models import SourceDocument, SourcePage, SourceTextElement
from plotter_processor.document_paginator import add_page_numbers, paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec


def test_page_numbers_are_two_pass_centered_and_sequential(test_font: Path) -> None:
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    document = SourceDocument(
        Path("long.txt"),
        (SourcePage(0, None, None, (SourceTextElement("text", 0, 0, ("word " * 150,)),)),),
    )
    page = PageSpec("test", 80, 55)
    with load_font(test_font) as font:
        result = paginate_document(
            document, font, page, config["margins_mm"], config["sizes"]["normal"],
            config["images"], config["pagination"], preserve_source_page_breaks=False,
        )
        add_page_numbers(
            result, font, page, config["margins_mm"], config["pagination"]["footer"],
            config["sizes"]["small"],
        )

    assert len(result.pages) >= 3
    assert [page.metadata["page_number_text"] for page in result.pages[:3]] == ["1", "2", "3"]
    assert all(
        page.metadata["page_number_center_x_mm"] == pytest.approx(40.0)
        for page in result.pages
    )


def test_page_number_format_supports_total_pages(test_font: Path) -> None:
    config = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    footer = dict(config["pagination"]["footer"])
    footer["format"] = "{page}/{pages}"
    document = SourceDocument(
        Path("short.txt"),
        (SourcePage(0, None, None, (SourceTextElement("text", 0, 0, ("Short",)),)),),
    )
    page = PageSpec("test", 80, 55)
    with load_font(test_font) as font:
        result = paginate_document(
            document, font, page, config["margins_mm"], config["sizes"]["normal"],
            config["images"], config["pagination"], preserve_source_page_breaks=False,
        )
        add_page_numbers(
            result, font, page, config["margins_mm"], footer,
            config["sizes"]["small"],
        )

    assert result.pages[0].metadata["page_number_text"] == "1/1"
