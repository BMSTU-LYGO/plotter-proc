from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageGrid:
    enabled: bool
    cell_width_mm: float = 0.0
    cell_height_mm: float = 0.0
    origin_x_mm: float = 0.0
    origin_y_mm: float = 0.0
    baseline_offset_mm: float = 0.0

    def baseline_at_or_after(self, minimum_y_mm: float) -> float:
        if not self.enabled:
            return minimum_y_mm
        first = self.origin_y_mm + self.baseline_offset_mm
        index = max(0, math.ceil((minimum_y_mm - first - 1e-9) / self.cell_height_mm))
        return first + index * self.cell_height_mm


def resolve_page_grid(values: Mapping[str, object] | None) -> PageGrid:
    config = values or {}
    enabled = config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise TypeError("grid.enabled must be boolean")
    if not enabled:
        return PageGrid(False)
    return PageGrid(
        True,
        _positive(config, "cell_width_mm"),
        _positive(config, "cell_height_mm"),
        _number(config, "origin_x_mm"),
        _number(config, "origin_y_mm"),
        _number(config, "baseline_offset_mm"),
    )


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"grid.{key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"grid.{key} must be finite")
    return number


def _positive(values: Mapping[str, object], key: str) -> float:
    number = _number(values, key)
    if number <= 0:
        raise ValueError(f"grid.{key} must be positive")
    return number
