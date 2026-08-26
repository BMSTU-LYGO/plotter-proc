from __future__ import annotations

from pathlib import Path

from plotter_processor.document_models import (
    DocumentMetadata,
    SourceBBox,
    SourceDocument,
    SourcePage,
    SourceVectorElement,
)
from plotter_processor.svg_importer import import_svg, svg_intrinsic_size_mm


def read_svg_document(path: Path) -> SourceDocument:
    width_mm, height_mm = svg_intrinsic_size_mm(path)
    element_id = "page-001-svg-001"
    strokes = import_svg(
        path,
        x_mm=0.0,
        y_mm=0.0,
        width_mm=width_mm,
        height_mm=height_mm,
        element_id=element_id,
    )
    bbox = SourceBBox(0.0, 0.0, width_mm, height_mm)
    vector = SourceVectorElement(
        element_id,
        0,
        0,
        tuple(strokes),
        bbox,
        "absolute",
        "none",
    )
    return SourceDocument(
        path,
        (SourcePage(0, width_mm, height_mm, (vector,), bbox),),
        metadata=DocumentMetadata(source_format="svg"),
    )
