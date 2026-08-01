from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from plotter_processor.job_models import PageJob, PlotterJob
from plotter_processor.models import PageSpec, PathDocument, PlotterStroke, Point
from plotter_processor.multipage_gcode_exporter import generate_job_gcode


def _job(count: int = 3) -> PlotterJob:
    page = PageSpec("A5", 148, 210)
    pages = [
        PageJob(
            index, index + 1,
            PathDocument(148, 210, [PlotterStroke(0, [Point(10, 10), Point(20, 20)], False)], []),
            (f"text-{index}",), [],
        )
        for index in range(count)
    ]
    return PlotterJob(page, pages, [])


def _machine() -> dict[str, object]:
    return yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))


def test_job_gcode_has_safe_page_change_sequence() -> None:
    gcode = generate_job_gcode(_job(), _machine())
    lines = gcode.splitlines()

    assert gcode.count("G4 P90000") == 2
    assert gcode.count("M84") == 1
    assert lines[-2] == "M84"
    for index, line in enumerate(lines):
        if line == "G4 P90000":
            assert lines[index - 2] == "M400"
            assert lines[index - 3].startswith("G0 X")
            assert any("Z5" in candidate for candidate in lines[max(0, index - 5):index])
    assert all(command not in gcode for command in ("M104", "M109", "M140", "M190", "G28"))
    assert not any(
        token.startswith("E") and token[1:].replace(".", "", 1).lstrip("-").isdigit()
        for line in lines for token in line.split()
    )


def test_job_command_limit_and_park_workspace_are_enforced() -> None:
    with pytest.raises(ValueError, match="safe limit"):
        generate_job_gcode(_job(), _machine(), max_commands=10)
    machine = deepcopy(_machine())
    machine["page_change"]["park"] = {"mode": "machine_point", "x_mm": 999, "y_mm": 10}
    with pytest.raises(ValueError, match="outside workspace"):
        generate_job_gcode(_job(2), machine)
