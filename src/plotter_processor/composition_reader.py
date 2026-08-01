from __future__ import annotations

from pathlib import Path

import yaml

from plotter_processor.composition_models import (
    DocumentElement,
    ElementPlacement,
    PlotterDocument,
    SvgElement,
    TextElement,
)


def read_composition(path: Path) -> PlotterDocument:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("Composition manifest requires version: 1")
    allowed_root = {"version", "page", "fonts", "elements"}
    if set(raw) - allowed_root:
        raise ValueError(f"Unknown manifest fields: {sorted(set(raw) - allowed_root)}")
    page = raw.get("page")
    if page not in {"A4", "A5"}:
        raise ValueError("Composition page must be A4 or A5")
    fonts = raw.get("fonts")
    if not isinstance(fonts, dict) or not isinstance(fonts.get("primary"), str):
        raise TypeError("Composition fonts.primary is required")
    base = path.resolve().parent
    primary = _relative(base, fonts["primary"], restrict=False)
    fallbacks: list[tuple[str, Path]] = []
    for item in fonts.get("fallbacks", []):
        if not isinstance(item, dict) or not isinstance(item.get("role"), str):
            raise TypeError("Each fallback requires role and path")
        fallbacks.append((item["role"], _relative(base, item.get("path"), restrict=False)))
    values = raw.get("elements")
    if not isinstance(values, list) or not values:
        raise ValueError("Composition requires at least one element")
    elements: list[DocumentElement] = []
    ids: set[str] = set()
    for order, item in enumerate(values):
        if not isinstance(item, dict):
            raise TypeError("Composition element must be a mapping")
        element_id = item.get("id")
        if not isinstance(element_id, str) or not element_id or element_id in ids:
            raise ValueError(f"Invalid or duplicate element id: {element_id!r}")
        ids.add(element_id)
        placement = ElementPlacement(
            _positive(item, "x_mm", allow_zero=True),
            _positive(item, "y_mm", allow_zero=True),
            _positive(item, "width_mm"),
            _optional_positive(item, "height_mm"),
        )
        common = {
            "id": element_id,
            "type": str(item.get("type")),
            "placement": placement,
            "z_order": int(item.get("z_order", order)),
            "travel_group": item.get("travel_group"),
            "preserve_stroke_order": bool(item.get("preserve_stroke_order", True)),
        }
        if item.get("type") == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError(f"Text element {element_id!r} requires text")
            elements.append(
                TextElement(
                    **common,
                    text=text,
                    size=str(item.get("size", "normal")),
                    font_mode=str(item.get("font_mode", "centerline")),
                )
            )
        elif item.get("type") == "svg":
            elements.append(
                SvgElement(
                    **common,
                    path=_relative(base, item.get("path"), restrict=True),
                    fit=str(item.get("fit", "contain")),
                )
            )
        else:
            raise ValueError(f"Unsupported element type: {item.get('type')!r}")
    elements.sort(key=lambda element: (element.z_order, values.index(next(v for v in values if v["id"] == element.id))))
    return PlotterDocument(1, page, primary, tuple(fallbacks), tuple(elements), path.resolve())


def _relative(base: Path, value: object, *, restrict: bool) -> Path:
    if not isinstance(value, str) or not value:
        raise TypeError("Manifest path must be a non-empty string")
    resolved = (base / value).resolve()
    if restrict and not resolved.is_relative_to(base):
        raise ValueError("Manifest path escapes its directory")
    return resolved


def _positive(values: dict, key: str, *, allow_zero: bool = False) -> float:
    value = values.get(key)
    minimum_ok = value >= 0 if allow_zero and isinstance(value, (int, float)) else False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (value > 0 or minimum_ok):
        raise ValueError(f"Invalid element dimension: {key}")
    return float(value)


def _optional_positive(values: dict, key: str) -> float | None:
    return None if key not in values else _positive(values, key)
