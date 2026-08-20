from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from plotter_processor.document_models import (
    SourceLineElement,
    SourceRasterImageElement,
    SourceTextElement,
)
from plotter_processor.structured_document_reader import read_structured_document


def _png(path: Path) -> None:
    image = Image.new("RGB", (48, 32), "white")
    ImageDraw.Draw(image).line((4, 4, 42, 26), fill="black", width=3)
    image.save(path)


def test_pdf_extracts_text_two_image_placements_and_vector_line(tmp_path: Path) -> None:
    png = tmp_path / "line.png"
    _png(png)
    source = tmp_path / "mixed.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((30, 30), "PDF document text")
    page.insert_image((30, 50, 90, 90), filename=str(png))
    page.insert_image((100, 50, 160, 90), filename=str(png))
    page.draw_line((30, 120), (160, 120))
    pdf.save(source)
    pdf.close()

    document = read_structured_document(source, assets_dir=tmp_path / "assets")
    elements = document.pages[0].elements

    assert any(isinstance(item, SourceTextElement) for item in elements)
    images = [item for item in elements if isinstance(item, SourceRasterImageElement)]
    assert len(images) == 2
    assert images[0].image_path == images[1].image_path
    lines = [item for item in elements if isinstance(item, SourceLineElement)]
    assert lines and lines[0].semantic_role == "line"


def test_complex_pdf_fill_is_rasterized_with_warning(tmp_path: Path) -> None:
    source = tmp_path / "filled.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.draw_rect((30, 30, 90, 70), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    pdf.save(source)
    pdf.close()

    result = read_structured_document(source, assets_dir=tmp_path / "assets")

    assert any(isinstance(item, SourceRasterImageElement) for item in result.elements)
    assert any("pdf_complex_drawing_rasterized" in warning for warning in result.warnings)
