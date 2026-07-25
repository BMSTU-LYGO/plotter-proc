from pathlib import Path
from xml.etree import ElementTree

import pytest

from plotter_processor.models import PathDocument, Point, Stroke
from plotter_processor.svg_exporter import export_svg

SVG_NAMESPACE = {"svg": "http://www.w3.org/2000/svg"}


def _document() -> PathDocument:
    return PathDocument(
        page_width_mm=210.0,
        page_height_mm=297.0,
        strokes=[
            Stroke(points=[Point(10.0, 20.0), Point(30.0, 40.0)], source_component=0),
            Stroke(points=[Point(50.0, 60.0), Point(70.0, 80.0)], source_component=1),
        ],
        warnings=[],
    )


def test_exports_physical_page_and_viewbox(tmp_path: Path) -> None:
    output = tmp_path / "preview.svg"

    export_svg(
        _document(),
        output,
        margins_mm={"left": 10, "right": 10, "top": 20, "bottom": 30},
    )

    root = ElementTree.parse(output).getroot()
    assert root.attrib["width"] == "210.0mm"
    assert root.attrib["height"] == "297.0mm"
    assert root.attrib["viewBox"] == "0 0 210.0 297.0"


def test_exports_strokes_starts_and_margin_frame(tmp_path: Path) -> None:
    output = tmp_path / "preview.svg"

    export_svg(
        _document(),
        output,
        margins_mm={"left": 10, "right": 10, "top": 20, "bottom": 30},
    )

    root = ElementTree.parse(output).getroot()
    assert len(root.findall("svg:polyline", SVG_NAMESPACE)) == 2
    assert len(root.findall("svg:circle", SVG_NAMESPACE)) == 2
    assert len(root.findall("svg:rect", SVG_NAMESPACE)) == 2
    assert root.findall("svg:line", SVG_NAMESPACE) == []


def test_optionally_exports_travel_movements(tmp_path: Path) -> None:
    output = tmp_path / "preview.svg"

    export_svg(
        _document(),
        output,
        margins_mm={"left": 10, "right": 10, "top": 20, "bottom": 30},
        show_travel=True,
    )

    root = ElementTree.parse(output).getroot()
    travel_lines = root.findall("svg:line", SVG_NAMESPACE)
    assert len(travel_lines) == 1
    assert travel_lines[0].attrib["x1"] == "30.0"
    assert travel_lines[0].attrib["y2"] == "60.0"


def test_rejects_invalid_margins(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no usable preview area"):
        export_svg(
            _document(),
            tmp_path / "preview.svg",
            margins_mm={"left": 110, "right": 110, "top": 20, "bottom": 30},
        )
