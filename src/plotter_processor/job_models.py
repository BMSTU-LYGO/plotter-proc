from __future__ import annotations

from dataclasses import dataclass, field

from plotter_processor.models import PageSpec, PathDocument


@dataclass(slots=True)
class PageJob:
    page_index: int
    page_number: int
    path_document: PathDocument
    source_element_ids: tuple[str, ...]
    warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class PlotterJob:
    page_spec: PageSpec
    pages: list[PageJob]
    warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)
