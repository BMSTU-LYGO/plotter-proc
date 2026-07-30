from pathlib import Path
from xml.etree import ElementTree

from plotter_processor.glyph_outline import ExactGlyphPath
from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.svg_exporter import export_font_preview, export_plotter_preview


def test_exports_exact_and_linear_svg(tmp_path: Path) -> None:
    exact = tmp_path / "font.svg"
    plotter = tmp_path / "plotter.svg"
    export_font_preview([ExactGlyphPath("Ё", "uni0401", 0, "M 1 1 Q 2 0 3 1 Z")], 148, 210, exact)
    export_plotter_preview(
        PathDocument(148, 210, [PlotterStroke(0, [Point(1, 1), Point(3, 1)], True, 0, "Ё", 0)], []),
        plotter,
    )
    exact_root = ElementTree.parse(exact).getroot()
    plotter_root = ElementTree.parse(plotter).getroot()
    assert exact_root.attrib["width"] == "148mm"
    assert (
        "Q" in next(element for element in exact_root if element.tag.endswith("path")).attrib["d"]
    )
    assert (
        next(element for element in plotter_root if element.tag.endswith("path"))
        .attrib["d"]
        .endswith("Z")
    )
