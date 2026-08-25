from __future__ import annotations

import cProfile
import pstats
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


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

    def record(self, stage: str, elapsed_ms: float, *, calls: int = 1) -> None:
        """Merge timing measured outside this process into the job report."""
        if stage not in self.REQUIRED_STAGES:
            raise ValueError(f"Unsupported stage: {stage}")
        metric = self.metrics.setdefault(stage, StageMetric())
        metric.calls += calls
        metric.total_ms += elapsed_ms
        metric.max_ms = max(metric.max_ms, elapsed_ms)


class HotspotTimings:
    """Optional fine-grained timings used by benchmarks and debug runs."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.metrics: dict[str, StageMetric] = {}

    @contextmanager
    def measure(self, hotspot: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - started) * 1000.0
            metric = self.metrics.setdefault(hotspot, StageMetric())
            metric.calls += 1
            metric.total_ms += elapsed
            metric.max_ms = max(metric.max_ms, elapsed)

    def report(self) -> dict[str, dict[str, int | float]]:
        return {
            name: {
                "calls": metric.calls,
                "total_ms": round(metric.total_ms, 3),
                "max_ms": round(metric.max_ms, 3),
            }
            for name, metric in sorted(self.metrics.items())
        }

    def record(self, hotspot: str, elapsed_ms: float) -> None:
        if not self.enabled:
            return
        metric = self.metrics.setdefault(hotspot, StageMetric())
        metric.calls += 1
        metric.total_ms += elapsed_ms
        metric.max_ms = max(metric.max_ms, elapsed_ms)


class FunctionProfiler:
    """Optional stdlib profiler for a whole run or one repeated pipeline stage."""

    PROFILE_STAGES = ("handwriting", "simplification", "build_paths", "font_compile")

    def __init__(self, stage: str | None = None) -> None:
        if stage is not None and stage not in self.PROFILE_STAGES:
            raise ValueError(f"Unsupported profile stage: {stage}")
        self.stage = stage
        self._profile = cProfile.Profile()
        self._active_calls = 0

    def start(self) -> None:
        if self.stage is None:
            self._profile.enable()

    def stop(self) -> None:
        self._profile.disable()
        self._active_calls = 0

    def progress(self, stage: str, state: str, elapsed_ms: float | None) -> None:
        del elapsed_ms
        if stage != self.stage:
            return
        if state == "started":
            if self._active_calls == 0:
                self._profile.enable()
            self._active_calls += 1
        elif state == "completed":
            self._active_calls -= 1
            if self._active_calls == 0:
                self._profile.disable()

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._profile.dump_stats(path)

    def top_functions(self, limit: int = 20) -> list[dict[str, object]]:
        stats = pstats.Stats(self._profile)
        rows = []
        for (filename, line, function), values in stats.stats.items():
            primitive_calls, calls, self_seconds, cumulative_seconds, _ = values
            rows.append(
                {
                    "function": f"{filename}:{line}({function})",
                    "calls": calls,
                    "primitive_calls": primitive_calls,
                    "self_seconds": round(self_seconds, 6),
                    "cumulative_seconds": round(cumulative_seconds, 6),
                    "seconds_per_call": round(self_seconds / calls, 9) if calls else 0.0,
                }
            )
        rows.sort(
            key=lambda row: (
                -float(row["cumulative_seconds"]),
                -float(row["self_seconds"]),
                str(row["function"]),
            )
        )
        return rows[:limit]


class PagePerformance:
    """Per-page workload counters and timings included in performance reports."""

    TIMINGS = (
        "build_paths_ms",
        "variation_ms",
        "word_routing_ms",
        "simplification_ms",
        "serialization_ms",
        "preview_ms",
        "gcode_ms",
    )
    COUNTERS = (
        "build_template_cache_hits",
        "build_template_cache_misses",
        "build_local_points_built",
        "build_output_points_allocated",
        "build_positioned_template_hits",
        "build_positioned_template_misses",
    )

    def __init__(
        self, page: int, glyph_count: int, *, collect_hotspots: bool = False
    ) -> None:
        self.hotspots = HotspotTimings(collect_hotspots)
        self.values: dict[str, int | float] = {
            "page": page,
            "glyph_count": glyph_count,
            "stroke_count_before": 0,
            "point_count_before": 0,
            "candidate_pairs": 0,
            "accepted_connections": 0,
            **{name: 0 for name in self.COUNTERS},
            **{name: 0.0 for name in self.TIMINGS},
        }

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        if name not in self.TIMINGS:
            raise ValueError(f"Unsupported per-page timing: {name}")
        started = time.perf_counter()
        try:
            yield
        finally:
            self.values[name] = float(self.values[name]) + (
                time.perf_counter() - started
            ) * 1000.0

    def report(self) -> dict[str, int | float]:
        report: dict[str, object] = {
            key: round(value, 3) if isinstance(value, float) else value
            for key, value in self.values.items()
        }
        if self.hotspots.enabled:
            report["hotspots"] = self.hotspots.report()
        return report


GLYPH_TIMING_STAGES = (
    "render",
    "mask",
    "label_components",
    "distance_transform",
    "candidate_1",
    "candidate_2",
    "spur_pruning",
    "graph_build",
    "graph_simplify",
    "routing",
    "smoothing",
    "quality",
    "serialization",
)


class GlyphPerformance:
    """Fine-grained cold compiler timings, enabled only by audit tools."""

    def __init__(self) -> None:
        self.current_glyph: str | None = None
        self.rows: dict[str, dict[str, object]] = {}

    @contextmanager
    def glyph(self, char: str) -> Iterator[None]:
        previous = self.current_glyph
        self.current_glyph = char
        row = self.rows.setdefault(
            char,
            {
                "glyph": char,
                "codepoint": f"U+{ord(char):04X}",
                "total_ms": 0.0,
                **{f"{stage}_ms": 0.0 for stage in GLYPH_TIMING_STAGES},
            },
        )
        started = time.perf_counter()
        try:
            yield
        finally:
            row["total_ms"] = float(row["total_ms"]) + (
                time.perf_counter() - started
            ) * 1000.0
            self.current_glyph = previous

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        if stage not in GLYPH_TIMING_STAGES:
            raise ValueError(f"Unsupported glyph timing: {stage}")
        char = self.current_glyph
        if char is None:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            key = f"{stage}_ms"
            row = self.rows[char]
            row[key] = float(row[key]) + (time.perf_counter() - started) * 1000.0

    def report(self) -> list[dict[str, object]]:
        return [
            {
                key: round(value, 3) if isinstance(value, float) else value
                for key, value in self.rows[char].items()
            }
            for char in sorted(self.rows, key=ord)
        ]


_GLYPH_PERFORMANCE: ContextVar[GlyphPerformance | None] = ContextVar(
    "glyph_performance", default=None
)


@contextmanager
def collect_glyph_performance() -> Iterator[GlyphPerformance]:
    performance = GlyphPerformance()
    token = _GLYPH_PERFORMANCE.set(performance)
    try:
        yield performance
    finally:
        _GLYPH_PERFORMANCE.reset(token)


@contextmanager
def glyph_performance(char: str) -> Iterator[None]:
    performance = _GLYPH_PERFORMANCE.get()
    if performance is None:
        yield
    else:
        with performance.glyph(char):
            yield


@contextmanager
def measure_glyph_stage(stage: str) -> Iterator[None]:
    performance = _GLYPH_PERFORMANCE.get()
    if performance is None:
        yield
    else:
        with performance.measure(stage):
            yield
