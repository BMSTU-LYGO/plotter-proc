from dataclasses import replace
from pathlib import Path

import pytest

from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.glyph_tuner import parameter_grid
from plotter_processor.config import load_yaml


def test_tuner_grid_is_bounded_and_deterministic() -> None:
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    config = replace(config, em_resolution_px=96)
    first = parameter_grid(config, 7)
    second = parameter_grid(config, 7)
    assert first == second
    assert len(first) == 7
    assert all(candidate["skeleton_method"] in {"skeletonize", "medial_axis"} for candidate in first)


def test_tuner_rejects_empty_sweep() -> None:
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    with pytest.raises(ValueError, match="positive"):
        parameter_grid(config, 0)
