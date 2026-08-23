from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(slots=True)
class StageMetric:
    calls: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0


class StageTimings:
    """Low-overhead per-job wall-clock timings."""

    REQUIRED_STAGES = (
        "read_document",
        "layout",
        "font_compile",
        "image_vectorization",
        "latex_render",
        "build_paths",
        "handwriting",
        "simplification",
        "preview",
        "gcode",
        "report",
    )

    def __init__(
        self,
        progress: Callable[[str, str, float | None], None] | None = None,
    ) -> None:
        self.started_at = time.perf_counter()
        self.metrics: dict[str, StageMetric] = {}
        self.progress = progress

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        if self.progress is not None:
            self.progress(stage, "started", None)
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - started) * 1000.0
            metric = self.metrics.setdefault(stage, StageMetric())
            metric.calls += 1
            metric.total_ms += elapsed
            metric.max_ms = max(metric.max_ms, elapsed)
            if self.progress is not None:
                self.progress(stage, "completed", elapsed)

    def report(self) -> dict[str, object]:
        elapsed = (time.perf_counter() - self.started_at) * 1000.0
        result: dict[str, object] = {"total_ms": round(elapsed, 3)}
        stages: dict[str, dict[str, object]] = {}
        for name in self.REQUIRED_STAGES:
            metric = self.metrics.get(name, StageMetric())
            result[f"{name}_ms"] = round(metric.total_ms, 3)
            stages[name] = {
                "calls": metric.calls,
                "total_ms": round(metric.total_ms, 3),
                "max_ms": round(metric.max_ms, 3),
            }
        result["stages"] = stages
        return result
