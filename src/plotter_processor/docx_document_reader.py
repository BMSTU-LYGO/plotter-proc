from __future__ import annotations

import hashlib
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image, UnidentifiedImageError

from plotter_processor.document_models import (
    SourceBBox,
    SourceDocument,
    SourceMathElement,
    SourcePage,
    SourceRasterImageElement,
    SourceTextElement,
)
from plotter_processor.omml_parser import parse_omml

EMU_PER_MM = 36000.0


def read_docx_document(path: Path, assets_dir: Path) -> SourceDocument:
    try:
        document = Document(path)
    except Exception as error:
        raise ValueError(f"Cannot read DOCX document: {path}") from error
    elements: list[SourceTextElement | SourceRasterImageElement | SourceMathElement] = []
    warnings: list[str] = []
    asset_cache: dict[str, Path] = {}
    body = document.element.body
    section = document.sections[0]
    page_width_mm = float(section.page_width) / EMU_PER_MM
    page_height_mm = float(section.page_height) / EMU_PER_MM
    margin_left_mm = float(section.left_margin) / EMU_PER_MM
    margin_right_mm = float(section.right_margin) / EMU_PER_MM
    margin_top_mm = float(section.top_margin) / EMU_PER_MM

    def add_text(text: str, *, table: bool = False) -> None:
        element_id = f"page-001-text-{len(elements) + 1:03d}"
        elements.append(SourceTextElement(element_id, len(elements), 0, (text,)))
        if table and "docx_table_layout_simplified" not in warnings:
            warnings.append("docx_table_layout_simplified")

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

    def walk_paragraph(paragraph: object, *, table: bool = False) -> None:
        buffer = ""
        emitted = False
        for child in paragraph.iterchildren():
            child_local = child.tag.rsplit("}", 1)[-1]
            if child_local in {"oMath", "oMathPara"}:
                if buffer:
                    add_text(buffer, table=table)
                    buffer = ""
                add_math(child)
                emitted = True
                continue
            if child.tag != qn("w:r"):
                continue
            for part in child.iterchildren():
                local = part.tag.rsplit("}", 1)[-1]
                if local in {"t", "tab", "br"}:
                    buffer += part.text or ("\t" if local == "tab" else "\n")
                elif local in {"drawing", "pict"}:
                    if buffer:
                        add_text(buffer, table=table)
                        emitted = True
                        buffer = ""
                    add_image(part)
                    emitted = True
        if buffer or not emitted:
            add_text(buffer, table=table)

    def walk_container(container: object, *, table: bool = False) -> None:
        for child in container.iterchildren():
            local = child.tag.rsplit("}", 1)[-1]
            if local == "p":
                walk_paragraph(child, table=table)
            elif local == "tbl":
                if "docx_table_layout_simplified" not in warnings:
                    warnings.append("docx_table_layout_simplified")
                for cell in child.xpath(".//*[local-name()='tc']"):
                    walk_container(cell, table=True)

    walk_container(body)
    return SourceDocument(
        path,
        (SourcePage(0, page_width_mm, page_height_mm, tuple(elements)),),
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
