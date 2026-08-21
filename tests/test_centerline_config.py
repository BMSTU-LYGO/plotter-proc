from pathlib import Path

import pytest

from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml


def test_loads_project_centerline_config() -> None:
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    assert config.em_resolution_px == 2048
    assert config.cache_directory == Path(".plotter-cache/font-cache")


def test_rejects_low_render_resolution() -> None:
    values = load_yaml(Path("configs/layout.yaml"))
    values["centerline"]["render"]["em_resolution_px"] = 511
    with pytest.raises(ValueError, match="em_resolution_px"):
        load_centerline_config(values)
