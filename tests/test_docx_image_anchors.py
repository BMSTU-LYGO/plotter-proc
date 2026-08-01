from pathlib import Path

import pytest

from plotter_processor.document_models import SourceRasterImageElement
from plotter_processor.structured_document_reader import read_structured_document


@pytest.mark.parametrize(
    ("name", "expected_x_side", "wrap_mode"),
    [
        ("image_left_wrap.docx", "left", "square"),
        ("image_right_wrap.docx", "right", "square"),
        ("image_top_bottom.docx", "center", "top_bottom"),
        ("image_absolute.docx", "right", "none"),
    ],
)
def test_docx_anchor_metadata_is_imported(
    tmp_path: Path, name: str, expected_x_side: str, wrap_mode: str
) -> None:
    document = read_structured_document(
        Path("tests/fixtures/update_7/images") / name,
        assets_dir=tmp_path / "assets",
    )
    image = next(
        item for item in document.elements if isinstance(item, SourceRasterImageElement)
    )

    assert image.bbox is not None
    assert image.bbox.coordinate_unit == "mm"
    assert image.anchor_type == "anchored"
    assert image.wrap_mode == wrap_mode
    center = (image.bbox.x0 + image.bbox.x1) / 2
    page_center = document.pages[0].width_mm / 2
    if expected_x_side == "left":
        assert center < page_center
    elif expected_x_side == "right":
        assert center > page_center
    else:
        assert abs(center - page_center) < 1
