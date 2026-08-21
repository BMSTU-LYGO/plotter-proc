from pathlib import Path

from plotter_processor.document_models import SourceArrowElement
from plotter_processor.structured_document_reader import read_structured_document


def test_docx_vml_arrow_direction_is_preserved(tmp_path: Path) -> None:
    document = read_structured_document(Path("tests/fixtures/update_7/lines_tables/arrows.docx"), assets_dir=tmp_path)
    arrow = next(item for item in document.elements if isinstance(item, SourceArrowElement))
    assert not arrow.head_at_start and arrow.head_at_end
    assert arrow.points[0].x_mm < arrow.points[-1].x_mm
