from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image, UnidentifiedImageError

from plotter_processor.document_models import (
    SourceArrowElement,
    SourceBBox,
    SourceDocument,
    SourceMathElement,
    SourcePage,
    SourceParagraph,
    SourcePoint,
    SourceRasterImageElement,
    SourceTableCell,
    SourceTableElement,
    SourceTextElement,
    SourceTextRun,
    SourceTextStyle,
)
from plotter_processor.omml_parser import parse_omml

EMU_PER_MM = 36000.0
TWIP_TO_MM = 25.4 / 1440.0


@dataclass(frozen=True, slots=True)
class _ParagraphFormat:
    alignment: str | None = None
    first_line_indent_mm: float | None = None
    hanging_indent_mm: float | None = None
    left_indent_mm: float | None = None
    right_indent_mm: float | None = None
    space_before_mm: float | None = None
    space_after_mm: float | None = None
    line_spacing: float | None = None
    tab_stops_mm: tuple[float, ...] | None = None


_ALIGNMENTS = {
    "left": "left", "start": "left",
    "right": "right", "end": "right",
    "center": "center", "both": "justify", "distribute": "justify",
}


def read_docx_document(path: Path, assets_dir: Path) -> SourceDocument:
    try:
        document = Document(path)
    except Exception as error:
        raise ValueError(f"Cannot read DOCX document: {path}") from error
    elements: list[
        SourceTextElement
        | SourceRasterImageElement
        | SourceMathElement
        | SourceArrowElement
        | SourceTableElement
    ] = []
    warnings: list[str] = []
    paragraph_resolver = _ParagraphFormatResolver(document, warnings)
    asset_cache: dict[str, Path] = {}
    body = document.element.body
    section = document.sections[0]
    page_width_mm = float(section.page_width) / EMU_PER_MM
    page_height_mm = float(section.page_height) / EMU_PER_MM
    margin_left_mm = float(section.left_margin) / EMU_PER_MM
    margin_right_mm = float(section.right_margin) / EMU_PER_MM
    margin_top_mm = float(section.top_margin) / EMU_PER_MM
    margin_bottom_mm = float(section.bottom_margin) / EMU_PER_MM

    def add_text(text: str, *, styled: SourceParagraph | None = None) -> None:
        element_id = f"page-001-text-{len(elements) + 1:03d}"
        elements.append(SourceTextElement(
            element_id,
            len(elements),
            0,
            (text,),
            styled_paragraphs=(styled,) if styled is not None else (),
        ))

    def add_image(drawing: object) -> None:
        blips = drawing.xpath(".//*[local-name()='blip']")
        if not blips:
            return
        relationship_id = blips[0].get(qn("r:embed"))
        if not relationship_id or relationship_id not in document.part.rels:
            warnings.append("docx_image_relationship_missing")
            return
        blob = document.part.rels[relationship_id].target_part.blob
        digest = hashlib.sha256(blob).hexdigest()[:12]
        if digest not in asset_cache:
            assets_dir.mkdir(parents=True, exist_ok=True)
            asset = assets_dir / f"image-{len(asset_cache) + 1:03d}-{digest}.png"
            try:
                import io

                with Image.open(io.BytesIO(blob)) as image:
                    image.save(asset, format="PNG")
            except (OSError, UnidentifiedImageError) as error:
                warnings.append(f"docx_image_decode_failed: {error}")
                return
            asset_cache[digest] = asset
        asset = asset_cache[digest]
        with Image.open(asset) as image:
            width_px, height_px = image.size
        extents = drawing.xpath(".//*[local-name()='extent']")
        width_mm = height_mm = None
        if extents:
            width_mm = float(extents[0].get("cx", 0)) / EMU_PER_MM or None
            height_mm = float(extents[0].get("cy", 0)) / EMU_PER_MM or None
        anchors = drawing.xpath(".//*[local-name()='anchor']")
        inlines = drawing.xpath(".//*[local-name()='inline']")
        container = anchors[0] if anchors else (inlines[0] if inlines else None)
        bbox = None
        anchor_type = "anchored" if anchors else "flow"
        wrap_mode = "inline"
        wrap_side = "both"
        distances = {"L": 0.0, "R": 0.0, "T": 0.0, "B": 0.0}
        relative_to_h = relative_to_v = None
        anchor_offset_x_mm = anchor_offset_y_mm = 0.0
        behind_text = False
        z_order = 0
        if anchors:
            anchor = anchors[0]
            position_h = anchor.xpath("./*[local-name()='positionH']")
            position_v = anchor.xpath("./*[local-name()='positionV']")
            relative_to_h = position_h[0].get("relativeFrom") if position_h else None
            relative_to_v = position_v[0].get("relativeFrom") if position_v else None
            x_values = anchor.xpath(
                "./*[local-name()='positionH']/*[local-name()='posOffset']/text()"
            )
            y_values = anchor.xpath(
                "./*[local-name()='positionV']/*[local-name()='posOffset']/text()"
            )
            if x_values:
                anchor_offset_x_mm = float(x_values[0]) / EMU_PER_MM
            if y_values:
                anchor_offset_y_mm = float(y_values[0]) / EMU_PER_MM
            h_align = anchor.xpath(
                "./*[local-name()='positionH']/*[local-name()='align']/text()"
            )
            v_align = anchor.xpath(
                "./*[local-name()='positionV']/*[local-name()='align']/text()"
            )
            x = _anchor_x(
                x_values,
                h_align,
                relative_to_h,
                page_width_mm,
                margin_left_mm,
                margin_right_mm,
                width_mm or 0.0,
            )
            y = _anchor_y(
                y_values,
                v_align,
                relative_to_v,
                page_height_mm,
                margin_top_mm,
                height_mm or 0.0,
            )
            bbox = SourceBBox(x, y, x + (width_mm or 0), y + (height_mm or 0))
            wrap_mode, wrap_side = _anchor_wrap(anchor, warnings)
            behind_text = anchor.get("behindDoc", "0") in {"1", "true"}
            if behind_text:
                wrap_mode = "square"
                warnings.append("docx_behind_text_approximated_as_square")
            z_order = int(anchor.get("relativeHeight", "0"))
            for key in distances:
                distances[key] = float(anchor.get(f"dist{key}", "0")) / EMU_PER_MM
        rotation = 0.0
        if container is not None:
            transforms = container.xpath(".//*[local-name()='xfrm']")
            if transforms and transforms[0].get("rot"):
                rotation = float(transforms[0].get("rot")) / 60000.0
        elements.append(SourceRasterImageElement(
            f"page-001-image-{len(elements) + 1:03d}", len(elements), 0, asset,
            width_px, height_px, width_mm, height_mm, bbox,
            anchor_type, wrap_mode, wrap_side,
            distances["L"], distances["R"], distances["T"], distances["B"],
            relative_to_h, relative_to_v, behind_text, z_order, rotation,
            anchor_offset_x_mm, anchor_offset_y_mm,
        ))

    def add_math(math: object) -> None:
        try:
            parsed = parse_omml(math)
        except ValueError as error:
            warnings.append(f"omml_equation_not_supported:{error}")
            return
        warnings.extend(parsed.warnings)
        elements.append(SourceMathElement(
            f"page-001-math-{len(elements) + 1:03d}",
            len(elements),
            0,
            parsed.expression,
            parsed.display_mode,
            "omml",
        ))

    def add_arrow(pict: object) -> bool:
        lines = pict.xpath(".//*[local-name()='line']")
        if not lines:
            return False
        pict_identity = f"page-001-pict-{len(elements) + 1:03d}"
        for line_index, line in enumerate(lines):
            start = _vml_point(line.get("from", "0,0"))
            end = _vml_point(line.get("to", "0,0"))
            strokes = line.xpath("./*[local-name()='stroke']")
            stroke = strokes[0] if strokes else line
            start_style = stroke.get("startarrow", "none")
            end_style = stroke.get("endarrow", "none")
            start_head = start_style != "none"
            end_head = end_style != "none"
            style = end_style if end_head else start_style if start_head else "open"
            width = line.get("strokeweight")
            elements.append(SourceArrowElement(
                f"page-001-arrow-{len(elements) + 1:03d}",
                len(elements),
                0,
                (start, end),
                start_head,
                end_head,
                style,
                SourceBBox(
                    min(start.x_mm, end.x_mm),
                    min(start.y_mm, end.y_mm),
                    max(start.x_mm, end.x_mm),
                    max(start.y_mm, end.y_mm),
                ),
                1.0,
                start_style,
                end_style,
                line.get("strokecolor"),
                _vml_length(width) if width else None,
                f"{pict_identity}:line-{line_index + 1:03d}",
            ))
        return True

    def walk_paragraph(paragraph: object, *, table: bool = False) -> None:
        runs: list[SourceTextRun] = []
        emitted = False

        def flush() -> None:
            nonlocal emitted
            if not runs:
                return
            styled = paragraph_resolver.resolve(paragraph, tuple(runs))
            add_text(styled.text, styled=styled)
            runs.clear()
            emitted = True

        for child in paragraph.iterchildren():
            child_local = child.tag.rsplit("}", 1)[-1]
            if child_local in {"oMath", "oMathPara"}:
                flush()
                add_math(child)
                emitted = True
                continue
            if child.tag != qn("w:r"):
                continue
            run_text = ""
            for part in child.iterchildren():
                local = part.tag.rsplit("}", 1)[-1]
                if local in {"t", "tab", "br"}:
                    run_text += part.text or ("\t" if local == "tab" else "\n")
                elif local in {"drawing", "pict"}:
                    if run_text:
                        runs.append(SourceTextRun(run_text, _run_style(child, warnings)))
                        run_text = ""
                    flush()
                    if local == "pict" and add_arrow(part):
                        emitted = True
                        continue
                    add_image(part)
                    emitted = True
            if run_text:
                runs.append(SourceTextRun(run_text, _run_style(child, warnings)))
        flush()
        if not emitted:
            add_text("", styled=paragraph_resolver.resolve(paragraph, ()))

    def walk_container(container: object, *, table: bool = False) -> None:
        for child in container.iterchildren():
            local = child.tag.rsplit("}", 1)[-1]
            if local == "p":
                walk_paragraph(child, table=table)
            elif local == "tbl":
                elements.append(
                    _parse_table(child, len(elements), warnings, paragraph_resolver)
                )

    walk_container(body)
    return SourceDocument(
        path,
        (
            SourcePage(
                0,
                page_width_mm,
                page_height_mm,
                tuple(elements),
                SourceBBox(
                    margin_left_mm,
                    margin_top_mm,
                    page_width_mm - margin_right_mm,
                    page_height_mm - margin_bottom_mm,
                ),
            ),
        ),
        tuple(dict.fromkeys(warnings)),
    )


def _anchor_x(
    offsets: list[str],
    aligns: list[str],
    relative_to: str | None,
    page_width: float,
    margin_left: float,
    margin_right: float,
    width: float,
) -> float:
    origin = margin_left if relative_to in {"margin", "column"} else 0.0
    extent = (
        page_width - margin_left - margin_right
        if relative_to in {"margin", "column"}
        else page_width
    )
    if offsets:
        return origin + float(offsets[0]) / EMU_PER_MM
    align = aligns[0] if aligns else "left"
    if align == "right":
        return origin + extent - width
    if align == "center":
        return origin + (extent - width) / 2
    return origin


def _anchor_y(
    offsets: list[str],
    aligns: list[str],
    relative_to: str | None,
    page_height: float,
    margin_top: float,
    height: float,
) -> float:
    if relative_to not in {"page", "margin"}:
        return 0.0
    origin = margin_top if relative_to == "margin" else 0.0
    extent = page_height - 2 * margin_top if relative_to == "margin" else page_height
    if offsets:
        return origin + float(offsets[0]) / EMU_PER_MM
    align = aligns[0] if aligns else "top"
    if align == "bottom":
        return origin + extent - height
    if align == "center":
        return origin + (extent - height) / 2
    return origin


def _anchor_wrap(anchor: object, warnings: list[str]) -> tuple[str, str]:
    for local, mode in (
        ("wrapSquare", "square"),
        ("wrapTight", "square"),
        ("wrapThrough", "square"),
        ("wrapTopAndBottom", "top_bottom"),
        ("wrapNone", "none"),
    ):
        nodes = anchor.xpath(f"./*[local-name()='{local}']")
        if not nodes:
            continue
        if local == "wrapTight":
            warnings.append("docx_wrap_tight_approximated_as_square")
        if local == "wrapThrough":
            warnings.append("docx_wrap_through_approximated_as_square")
        value = nodes[0].get("wrapText", "bothSides")
        side = {"left": "left", "right": "right"}.get(value, "both")
        return mode, side
    return "square", "both"


def _run_style(run: object, warnings: list[str]) -> SourceTextStyle:
    properties = run.find(qn("w:rPr"))
    if properties is None:
        return SourceTextStyle()
    underline_node = properties.find(qn("w:u"))
    underline = None
    if underline_node is not None:
        raw = underline_node.get(qn("w:val"), "single")
        if raw not in {"none", "false", "0"}:
            if raw in {"single", "double", "words"}:
                underline = raw
            else:
                underline = "single"
                warnings.append(f"docx_underline_style_approximated:{raw}")
    size_node = properties.find(qn("w:sz"))
    size = float(size_node.get(qn("w:val"))) / 2 if size_node is not None else None
    vertical = properties.find(qn("w:vertAlign"))
    return SourceTextStyle(
        underline=underline,
        strike=properties.find(qn("w:strike")) is not None,
        bold=properties.find(qn("w:b")) is not None,
        italic=properties.find(qn("w:i")) is not None,
        font_size_pt=size,
        baseline_shift=vertical.get(qn("w:val")) if vertical is not None else None,
    )


class _ParagraphFormatResolver:
    """Resolve effective DOCX paragraph properties without leaking Word styles downstream."""

    def __init__(self, document: object, warnings: list[str]) -> None:
        self.warnings = warnings
        styles_root = document.styles.element
        defaults = styles_root.xpath(
            "./*[local-name()='docDefaults']/*[local-name()='pPrDefault']/*[local-name()='pPr']"
        )
        self.defaults = _read_paragraph_properties(defaults[0], warnings) if defaults else _ParagraphFormat()
        self.styles: dict[str, object] = {}
        for style in styles_root.xpath("./*[local-name()='style']"):
            style_id = style.get(qn("w:styleId"))
            if style_id:
                self.styles[str(style_id)] = style

    def resolve(self, paragraph: object, runs: tuple[SourceTextRun, ...]) -> SourceParagraph:
        ppr = paragraph.find(qn("w:pPr"))
        style_id = None
        if ppr is not None:
            style_node = ppr.find(qn("w:pStyle"))
            if style_node is not None:
                style_id = style_node.get(qn("w:val"))
        style_chain = self._style_chain(style_id)
        effective = self.defaults
        style_name = None
        for style in style_chain:
            names = style.xpath("./*[local-name()='name']/@*[local-name()='val']")
            if names:
                style_name = str(names[0])
            properties = style.xpath("./*[local-name()='pPr']")
            if properties:
                effective = _merge_paragraph_format(
                    effective, _read_paragraph_properties(properties[0], self.warnings)
                )
        if ppr is not None:
            effective = _merge_paragraph_format(
                effective, _read_paragraph_properties(ppr, self.warnings)
            )
        role = _semantic_role(style_id, style_name)
        return SourceParagraph(
            runs=runs,
            alignment=effective.alignment,
            first_line_indent_mm=effective.first_line_indent_mm,
            hanging_indent_mm=effective.hanging_indent_mm,
            left_indent_mm=effective.left_indent_mm,
            right_indent_mm=effective.right_indent_mm,
            space_before_mm=effective.space_before_mm,
            space_after_mm=effective.space_after_mm,
            line_spacing=effective.line_spacing,
            tab_stops_mm=effective.tab_stops_mm or (),
            style_id=style_id,
            style_name=style_name,
            semantic_role=role,
        )

    def _style_chain(self, style_id: str | None) -> list[object]:
        chain: list[object] = []
        seen: set[str] = set()
        current = style_id
        while current and current not in seen and current in self.styles:
            seen.add(current)
            style = self.styles[current]
            chain.append(style)
            based_on = style.xpath("./*[local-name()='basedOn']/@*[local-name()='val']")
            current = str(based_on[0]) if based_on else None
        if current in seen:
            self.warnings.append(f"docx_paragraph_style_cycle:{current}")
        chain.reverse()
        return chain


def _read_paragraph_properties(properties: object, warnings: list[str]) -> _ParagraphFormat:
    alignment_values = properties.xpath("./*[local-name()='jc']/@*[local-name()='val']")
    alignment = None
    if alignment_values:
        raw_alignment = str(alignment_values[0])
        alignment = _ALIGNMENTS.get(raw_alignment, "left")
        if raw_alignment not in _ALIGNMENTS:
            warnings.append(f"docx_paragraph_alignment_approximated:{raw_alignment}")

    indent_nodes = properties.xpath("./*[local-name()='ind']")
    indent = indent_nodes[0] if indent_nodes else None
    spacing_nodes = properties.xpath("./*[local-name()='spacing']")
    spacing = spacing_nodes[0] if spacing_nodes else None
    tabs: list[float] | None = None
    tab_nodes = properties.xpath("./*[local-name()='tabs']/*[local-name()='tab']")
    if tab_nodes:
        tabs = []
        for tab in tab_nodes:
            kind = tab.get(qn("w:val"), "left")
            position = tab.get(qn("w:pos"))
            if kind == "clear":
                if position is not None:
                    cleared = float(position) * TWIP_TO_MM
                    tabs = [value for value in tabs if abs(value - cleared) > 1e-6]
                continue
            if kind != "left":
                warnings.append(f"docx_tab_stop_approximated:{kind}")
            if position is not None and kind != "bar":
                tabs.append(float(position) * TWIP_TO_MM)

    line_spacing = None
    if spacing is not None and spacing.get(qn("w:line")) is not None:
        raw_line = float(spacing.get(qn("w:line")))
        rule = spacing.get(qn("w:lineRule"), "auto")
        if rule == "auto":
            line_spacing = raw_line / 240.0
        else:
            warnings.append(f"docx_line_spacing_approximated:{rule}")
            line_spacing = max(1.0, raw_line / 240.0)

    return _ParagraphFormat(
        alignment=alignment,
        first_line_indent_mm=_twip_attribute(indent, "firstLine"),
        hanging_indent_mm=_twip_attribute(indent, "hanging"),
        left_indent_mm=_twip_attribute(indent, "left", "start"),
        right_indent_mm=_twip_attribute(indent, "right", "end"),
        space_before_mm=_twip_attribute(spacing, "before"),
        space_after_mm=_twip_attribute(spacing, "after"),
        line_spacing=line_spacing,
        tab_stops_mm=tuple(sorted(set(tabs))) if tabs is not None else None,
    )


def _twip_attribute(node: object | None, *names: str) -> float | None:
    if node is None:
        return None
    for name in names:
        value = node.get(qn(f"w:{name}"))
        if value is not None:
            return float(value) * TWIP_TO_MM
    return None


def _merge_paragraph_format(
    base: _ParagraphFormat, override: _ParagraphFormat
) -> _ParagraphFormat:
    values = {
        field: getattr(override, field)
        if getattr(override, field) is not None
        else getattr(base, field)
        for field in _ParagraphFormat.__dataclass_fields__
    }
    return _ParagraphFormat(**values)


def _semantic_role(style_id: str | None, style_name: str | None) -> str:
    normalized = " ".join(filter(None, (style_id, style_name))).casefold().replace("_", " ")
    if "title" in normalized or "назван" in normalized:
        return "title"
    for level in (1, 2, 3):
        if any(
            marker in normalized
            for marker in (f"heading {level}", f"heading{level}", f"заголовок {level}")
        ):
            return f"heading_{level}"
    return "body"


def _vml_point(value: str) -> SourcePoint:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Invalid VML point: {value}")
    return SourcePoint(*(_vml_length(part) for part in parts))


def _vml_length(value: str) -> float:
    if value.endswith("pt"):
        return float(value[:-2]) * 25.4 / 72
    if value.endswith("mm"):
        return float(value[:-2])
    return float(value) * 25.4 / 72


def _parse_table(
    table: object,
    order: int,
    warnings: list[str],
    paragraph_resolver: _ParagraphFormatResolver,
) -> SourceTableElement:
    grid_values = table.xpath(
        "./*[local-name()='tblGrid']/*[local-name()='gridCol']/@*[local-name()='w']"
    )
    column_widths = tuple(float(value) * 25.4 / 1440 for value in grid_values)
    rows = table.xpath("./*[local-name()='tr']")
    properties = table.xpath("./*[local-name()='tblPr']")
    properties = properties[0] if properties else None
    preferred_width = _table_width_mm(properties, "tblW")
    alignment_values = (
        properties.xpath("./*[local-name()='jc']/@*[local-name()='val']")
        if properties is not None else []
    )
    alignment = str(alignment_values[0]) if alignment_values else None
    if alignment in {"start"}:
        alignment = "left"
    elif alignment in {"end"}:
        alignment = "right"
    elif alignment not in {None, "left", "center", "right"}:
        warnings.append(f"docx_table_alignment_approximated:{alignment}")
        alignment = "left"
    left_indent = _table_width_mm(properties, "tblInd")
    row_heights: list[float | None] = []
    columns = len(column_widths)
    mutable_cells: list[dict[str, object]] = []
    active_vertical: dict[int, dict[str, object]] = {}
    repeat_headers = 0
    for row_index, row in enumerate(rows):
        height_values = row.xpath(
            "./*[local-name()='trPr']/*[local-name()='trHeight']/@*[local-name()='val']"
        )
        row_heights.append(float(height_values[0]) * TWIP_TO_MM if height_values else None)
        if (
            row.xpath("./*[local-name()='trPr']/*[local-name()='tblHeader']")
            and row_index == repeat_headers
        ):
            repeat_headers += 1
        column = 0
        for cell in row.xpath("./*[local-name()='tc']"):
            span_values = cell.xpath(
                "./*[local-name()='tcPr']/*[local-name()='gridSpan']/@*[local-name()='val']"
            )
            column_span = int(span_values[0]) if span_values else 1
            merge_nodes = cell.xpath("./*[local-name()='tcPr']/*[local-name()='vMerge']")
            merge_value = (
                merge_nodes[0].get(qn("w:val"), "continue") if merge_nodes else None
            )
            if merge_value == "continue" and column in active_vertical:
                active_vertical[column]["row_span"] = int(
                    active_vertical[column]["row_span"]
                ) + 1
                column += column_span
                continue
            paragraphs = tuple(
                _xml_paragraph_model(paragraph, warnings, paragraph_resolver)
                for paragraph in cell.xpath("./*[local-name()='p']")
            ) or (SourceParagraph(()),)
            width_values = cell.xpath(
                "./*[local-name()='tcPr']/*[local-name()='tcW']/@*[local-name()='w']"
            )
            entry: dict[str, object] = {
                "row": row_index,
                "column": column,
                "row_span": 1,
                "column_span": column_span,
                "paragraphs": paragraphs,
                "width_mm": float(width_values[0]) * 25.4 / 1440 if width_values else None,
                "height_mm": row_heights[-1],
                "vertical_alignment": _cell_vertical_alignment(cell, warnings),
            }
            mutable_cells.append(entry)
            if merge_value == "restart":
                active_vertical[column] = entry
            elif merge_nodes:
                active_vertical.pop(column, None)
            column += column_span
        columns = max(columns, column)
    if not column_widths:
        column_widths = tuple(0.0 for _ in range(columns))
    cells = tuple(SourceTableCell(**entry) for entry in mutable_cells)
    if table.xpath(".//*[local-name()='tbl']"):
        warnings.append("docx_nested_table_not_supported")
    return SourceTableElement(
        f"page-001-table-{order + 1:03d}",
        order,
        0,
        len(rows),
        columns,
        cells,
        column_widths,
        repeat_header_rows=repeat_headers,
        alignment=alignment,
        left_indent_mm=left_indent,
        preferred_width_mm=preferred_width,
        row_heights_mm=tuple(row_heights),
    )


def _table_width_mm(properties: object | None, local_name: str) -> float | None:
    if properties is None:
        return None
    nodes = properties.xpath(f"./*[local-name()='{local_name}']")
    if not nodes:
        return None
    kind = nodes[0].get(qn("w:type"), "dxa")
    value = nodes[0].get(qn("w:w"))
    if value is None or kind in {"auto", "nil"}:
        return None
    if kind == "pct":
        return None
    return float(value) * TWIP_TO_MM


def _cell_vertical_alignment(cell: object, warnings: list[str]) -> str | None:
    values = cell.xpath(
        "./*[local-name()='tcPr']/*[local-name()='vAlign']/@*[local-name()='val']"
    )
    if not values:
        return None
    value = str(values[0])
    if value in {"top", "center", "bottom"}:
        return value
    warnings.append(f"docx_cell_vertical_alignment_approximated:{value}")
    return "top"


def _xml_paragraph_model(
    paragraph: object,
    warnings: list[str],
    paragraph_resolver: _ParagraphFormatResolver,
) -> SourceParagraph:
    runs: list[SourceTextRun] = []
    for run in paragraph.xpath("./*[local-name()='r']"):
        parts: list[str] = []
        for child in run.iterchildren():
            local = child.tag.rsplit("}", 1)[-1]
            if local == "t":
                parts.append(child.text or "")
            elif local == "tab":
                parts.append("\t")
            elif local == "br":
                parts.append("\n")
        text = "".join(parts)
        if text:
            runs.append(SourceTextRun(text, _run_style(run, warnings)))
        if run.xpath(".//*[local-name()='drawing' or local-name()='pict']"):
            warnings.append("docx_table_embedded_object_not_supported")
    return paragraph_resolver.resolve(paragraph, tuple(runs))
