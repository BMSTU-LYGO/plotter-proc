from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from plotter_processor.stage_cache import file_sha256, stage_fingerprint

DOCUMENT_STAGE_VERSION = "document-model-v1"
LAYOUT_STAGE_VERSION = "layout-model-v1"
GEOMETRY_STAGE_VERSION = "final-geometry-v1"


def document_stage_fingerprint(
    input_path: Path,
    *,
    pdf_math_mode: str,
    pdf_math_options: Mapping[str, object],
) -> str:
    extension = input_path.suffix.lower()
    settings: dict[str, object] = {"format": extension or ".txt"}
    if extension == ".pdf":
        settings.update(
            {
                "pdf_math_mode": pdf_math_mode,
                "pdf_math_options": dict(pdf_math_options),
            }
        )
    return stage_fingerprint(
        "read_document",
        input_fingerprint=file_sha256(input_path),
        algorithm_version=DOCUMENT_STAGE_VERSION,
        settings=settings,
    )


def layout_stage_fingerprint(
    document_fingerprint: str,
    *,
    font_path: Path,
    settings: Mapping[str, object],
) -> str:
    return stage_fingerprint(
        "layout",
        input_fingerprint=document_fingerprint,
        algorithm_version=LAYOUT_STAGE_VERSION,
        settings={"font_sha256": file_sha256(font_path), **dict(settings)},
    )


def geometry_stage_fingerprint(
    layout_fingerprint: str,
    *,
    settings: Mapping[str, object],
) -> str:
    return stage_fingerprint(
        "geometry",
        input_fingerprint=layout_fingerprint,
        algorithm_version=GEOMETRY_STAGE_VERSION,
        settings=settings,
    )
