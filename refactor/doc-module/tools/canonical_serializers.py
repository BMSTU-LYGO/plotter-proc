"""Stable JSON encoders for C++ document-pipeline parity snapshots.

The encoders deliberately preserve list order: page order, source order and stroke
order are part of the pipeline contract.  Mapping keys are sorted and floats are
rounded to six decimal places so snapshots are portable across Python versions.
"""
from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any

_PATH_MARKERS = ("source", "input", "font", "path", "directory", "output", "cache")


def canonical_data(value: Any, *, roots: dict[Path, str] | None = None) -> Any:
    """Convert Python pipeline objects into deterministic JSON-compatible values."""
    roots = roots or {}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    if isinstance(value, Path):
        return _canonical_path(value, roots)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Parity snapshots cannot encode non-finite floats")
        return round(value, 6)
    if isinstance(value, dict):
        return {
            str(key): canonical_data(item, roots=roots)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [canonical_data(item, roots=roots) for item in value]
    if isinstance(value, set):
        return [canonical_data(item, roots=roots) for item in sorted(value, key=repr)]
    return value


def canonical_document(document: Any, *, roots: dict[Path, str]) -> dict[str, Any]:
    return {"stage": "document", "document": canonical_data(document, roots=roots)}


def canonical_layout(model: Any, placement: Any, trace: Any, report: Any, *, roots: dict[Path, str]) -> dict[str, Any]:
    report_data = canonical_data(report, roots=roots)
    return {
        "stage": "layout",
        "model": canonical_data(model, roots=roots),
        "placement": canonical_data(placement, roots=roots),
        "trace": canonical_data(trace, roots=roots),
        "summary": {
            "document_import": report_data.get("document_import", {}),
            "document_layout": report_data.get("document_layout", {}),
            "pagination": report_data.get("pagination", {}),
        },
    }


def canonical_paths(payload: Any, *, roots: dict[Path, str]) -> dict[str, Any]:
    return {"stage": "paths", "paths": canonical_data(payload, roots=roots)}


def canonical_job(payload: Any, *, roots: dict[Path, str]) -> dict[str, Any]:
    return {"stage": "job", "job": canonical_data(payload, roots=roots)}


def canonical_report(payload: Any, *, roots: dict[Path, str]) -> dict[str, Any]:
    """Keep semantic report fields while removing runtime timings and local paths."""
    return {"stage": "report", "report": canonical_data(_without_runtime_fields(payload), roots=roots)}


def _without_runtime_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_runtime_fields(item)
            for key, item in value.items()
            if key not in {"cache", "outputs", "performance"}
        }
    if isinstance(value, list):
        return [_without_runtime_fields(item) for item in value]
    return value


def write_canonical_json(path: Path, payload: Any, *, roots: dict[Path, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(canonical_data(payload, roots=roots), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _canonical_path(path: Path, roots: dict[Path, str]) -> str:
    resolved = path.resolve()
    for root, marker in sorted(roots.items(), key=lambda pair: len(str(pair[0])), reverse=True):
        try:
            suffix = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return marker if suffix == Path(".") else f"{marker}/{suffix.as_posix()}"
    return f"<external>/{path.name}"
