from pathlib import Path
from xml.etree import ElementTree

from plotter_processor.glyph_outline import ExactGlyphPath
from plotter_processor.models import PathDocument, PlotterStroke

SVG_NS = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", SVG_NS)


def export_font_preview(
    outlines: list[ExactGlyphPath],
    page_width_mm: float,
    page_height_mm: float,
    output_path: str | Path,
    *,
    show_page_border: bool = True,
) -> None:
    root = _svg_root(page_width_mm, page_height_mm, show_page_border)
    for outline in outlines:
        ElementTree.SubElement(
            root,
            _tag("path"),
            {
                "d": outline.path_data,
                "fill": "black",
                "stroke": "none",
                "data-char": outline.char,
                "data-glyph-name": outline.glyph_name,
                "data-glyph-index": str(outline.glyph_index),
            },
        )
    _write_svg(root, output_path)


def export_plotter_preview(
    document: PathDocument,
    output_path: str | Path,
    *,
    stroke_width_mm: float = 0.2,
    show_page_border: bool = True,
) -> None:
    if stroke_width_mm <= 0:
        raise ValueError("Plotter preview stroke width must be positive")
    root = _svg_root(document.page_width_mm, document.page_height_mm, show_page_border)
    for stroke in document.strokes:
        if not isinstance(stroke, PlotterStroke) or len(stroke.points) < 2:
            continue
        commands = [f"M {_fmt(stroke.points[0].x)} {_fmt(stroke.points[0].y)}"]
        commands.extend(f"L {_fmt(point.x)} {_fmt(point.y)}" for point in stroke.points[1:])
        if stroke.closed:
            commands.append("Z")
        attributes = {
            "d": " ".join(commands),
            "fill": "none",
            "stroke": "black",
            "stroke-width": _fmt(stroke_width_mm),
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "data-stroke-id": str(stroke.id),
            "data-contour-index": str(stroke.contour_index),
        }
        if stroke.char is not None:
            attributes["data-char"] = stroke.char
        if stroke.glyph_index is not None:
            attributes["data-glyph-index"] = str(stroke.glyph_index)
        if stroke.element_id is not None:
            attributes["data-element-id"] = stroke.element_id
        if stroke.element_type is not None:
            attributes["data-element-type"] = stroke.element_type
        if stroke.font_role is not None:
            attributes["data-font-role"] = stroke.font_role
        ElementTree.SubElement(root, _tag("path"), attributes)
    _write_svg(root, output_path)


def _svg_root(width: float, height: float, show_page_border: bool) -> ElementTree.Element:
    if width <= 0 or height <= 0:
        raise ValueError("SVG page dimensions must be positive")
    root = ElementTree.Element(
        _tag("svg"),
        {"width": f"{width}mm", "height": f"{height}mm", "viewBox": f"0 0 {width} {height}"},
    )
    ElementTree.SubElement(
        root, _tag("rect"), {"width": str(width), "height": str(height), "fill": "white"}
    )
    if show_page_border:
        ElementTree.SubElement(
            root,
            _tag("rect"),
            {
                "x": "0.075",
                "y": "0.075",
                "width": _fmt(width - 0.15),
                "height": _fmt(height - 0.15),
                "fill": "none",
                "stroke": "#999",
                "stroke-width": "0.15",
            },
        )
    return root


def _write_svg(root: ElementTree.Element, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ElementTree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")
