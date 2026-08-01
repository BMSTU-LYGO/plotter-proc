from __future__ import annotations

import hashlib
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image, UnidentifiedImageError

from plotter_processor.document_models import (
    SourceBBox,
    SourceDocument,
    SourcePage,
    SourceRasterImageElement,
    SourceTextElement,
)

EMU_PER_MM = 36000.0


def read_docx_document(path: Path, assets_dir: Path) -> SourceDocument:
    try:
        document = Document(path)
    except Exception as error:
        raise ValueError(f"Cannot read DOCX document: {path}") from error
    elements: list[SourceTextElement | SourceRasterImageElement] = []
    warnings: list[str] = []
    asset_cache: dict[str, Path] = {}
    body = document.element.body

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
        bbox = None
        if anchors:
            x_values = anchors[0].xpath(".//*[local-name()='positionH']/*[local-name()='posOffset']/text()")
            y_values = anchors[0].xpath(".//*[local-name()='positionV']/*[local-name()='posOffset']/text()")
            x = float(x_values[0]) / EMU_PER_MM if x_values else 0.0
            y = float(y_values[0]) / EMU_PER_MM if y_values else 0.0
            bbox = SourceBBox(x, y, x + (width_mm or 0), y + (height_mm or 0))
            warnings.append("floating_image_reflowed")
        elements.append(SourceRasterImageElement(
            f"page-001-image-{len(elements) + 1:03d}", len(elements), 0, asset,
            width_px, height_px, width_mm, height_mm, bbox,
        ))

    def walk_paragraph(paragraph: object, *, table: bool = False) -> None:
        buffer = ""
        emitted = False
        for child in paragraph.iterchildren():
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
    return SourceDocument(path, (SourcePage(0, None, None, tuple(elements)),), tuple(dict.fromkeys(warnings)))
