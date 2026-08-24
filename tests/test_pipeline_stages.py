from plotter_processor.performance import StageTimings
from plotter_processor.pipeline_stages import (
    CORE_STAGES,
    NORMALIZE_LAYOUT,
    READ_DOCUMENT,
    StageExecutor,
)


def test_core_pipeline_stages_have_explicit_model_boundaries() -> None:
    assert [stage.name for stage in CORE_STAGES] == [
        "read_document",
        "layout",
        "build_paths",
        "handwriting",
        "simplification",
        "gcode",
    ]
    assert READ_DOCUMENT.input_model == "InputDocument"
    assert READ_DOCUMENT.output_model == "DocumentModel"
    assert NORMALIZE_LAYOUT.input_model == "DocumentModel"
    assert NORMALIZE_LAYOUT.output_model == "LayoutModel"


def test_stage_executor_collects_timing_and_metadata() -> None:
    timings = StageTimings()
    executor = StageExecutor(timings)

    result = executor.run(
        READ_DOCUMENT,
        "source.docx",
        lambda value: {"source": value},
        metadata={"format": ".docx"},
    )

    assert result == {"source": "source.docx"}
    assert timings.report()["stages"]["read_document"]["calls"] == 1
    assert executor.report()["read_document"] == {
        "input": "InputDocument",
        "output": "DocumentModel",
        "calls": 1,
        "metadata": [{"format": ".docx"}],
    }
