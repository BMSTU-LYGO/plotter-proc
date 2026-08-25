from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from plotter_processor.performance import StageTimings
from plotter_processor.stage_cache import StageCacheManager

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class StageDefinition(Generic[InputT, OutputT]):
    """Stable boundary between two pipeline data models."""

    name: str
    input_model: str
    output_model: str


READ_DOCUMENT = StageDefinition[object, object](
    "read_document", "InputDocument", "DocumentModel"
)
NORMALIZE_LAYOUT = StageDefinition[object, object](
    "layout", "DocumentModel", "LayoutModel"
)
BUILD_PATHS = StageDefinition[object, object](
    "build_paths", "LayoutPage", "PathGeometry"
)
HANDWRITING = StageDefinition[object, object](
    "handwriting", "PathGeometry", "HandwritingGeometry"
)
SIMPLIFICATION_ROUTING = StageDefinition[object, object](
    "simplification", "HandwritingGeometry", "FinalGeometry"
)
GENERATE_GCODE = StageDefinition[object, object](
    "gcode", "FinalGeometry", "GCode"
)

CORE_STAGES = (
    READ_DOCUMENT,
    NORMALIZE_LAYOUT,
    BUILD_PATHS,
    HANDWRITING,
    SIMPLIFICATION_ROUTING,
    GENERATE_GCODE,
)


@dataclass(slots=True)
class StageExecution:
    calls: int = 0
    metadata: list[dict[str, object]] = field(default_factory=list)


class StageExecutor:
    """Executes named stages through one timing and metadata mechanism."""

    def __init__(self, timings: StageTimings) -> None:
        self.timings = timings
        self.executions: dict[str, StageExecution] = {}

    def run(
        self,
        stage: StageDefinition[InputT, OutputT],
        value: InputT,
        operation: Callable[[InputT], OutputT],
        *,
        metadata: dict[str, object] | None = None,
    ) -> OutputT:
        with self.timings.measure(stage.name):
            result = operation(value)
        execution = self.executions.setdefault(stage.name, StageExecution())
        execution.calls += 1
        if metadata:
            execution.metadata.append(dict(metadata))
        return result

    def run_cached(
        self,
        stage: StageDefinition[InputT, OutputT],
        value: InputT,
        operation: Callable[[InputT], OutputT],
        *,
        cache: StageCacheManager,
        fingerprint: str,
        metadata: dict[str, object] | None = None,
    ) -> OutputT:
        lookup = cache.load(stage.name, fingerprint)
        cache_metadata = {**(metadata or {}), "cache": "hit" if lookup.hit else "miss"}
        if lookup.hit:
            return self.run(
                stage,
                value,
                lambda _: lookup.value,  # type: ignore[return-value]
                metadata=cache_metadata,
            )
        result = self.run(stage, value, operation, metadata=cache_metadata)
        cache.store(stage.name, fingerprint, result)
        return result

    def report(self) -> dict[str, dict[str, object]]:
        return {
            stage.name: {
                "input": stage.input_model,
                "output": stage.output_model,
                "calls": self.executions.get(stage.name, StageExecution()).calls,
                "metadata": self.executions.get(
                    stage.name, StageExecution()
                ).metadata,
            }
            for stage in CORE_STAGES
        }
