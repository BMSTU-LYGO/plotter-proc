from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from plotter_processor.centerline_font.compiler import _config_for_glyph
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.skeleton_selector import select_best_skeleton
from plotter_processor.config import load_yaml


def _config():
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    return replace(config, em_resolution_px=128, padding_px=8, min_branch_width_factor=0)


def test_candidate_selection_reports_geometry_and_topology_metrics() -> None:
    mask = np.zeros((31, 31), dtype=bool)
    mask[5:26, 12:19] = True
    mask[12:19, 5:26] = True
    selected = select_best_skeleton(mask, _config())
    assert selected.method in {"skeletonize", "medial_axis"}
    assert set(selected.candidate_metrics) == {"skeletonize", "medial_axis"}
    for metrics in selected.candidate_metrics.values():
        assert 0 <= metrics["mask_coverage"] <= 1
        assert metrics["endpoint_count"] >= 0
        assert metrics["junction_count"] >= 0
        assert metrics["component_count"] == 1


def test_glyph_override_is_local_and_validated() -> None:
    base = _config()
    overridden = replace(
        base,
        glyph_overrides={"ж": {"skeleton_method": "medial_axis", "simplify_tolerance_px": 0.7}},
    )
    glyph = _config_for_glyph(overridden, "ж")
    other = _config_for_glyph(overridden, "а")
    assert glyph.skeleton_method == "medial_axis"
    assert glyph.simplify_tolerance_px == 0.7
    assert other is overridden
    with pytest.raises(ValueError, match="Invalid skeleton_method"):
        _config_for_glyph(replace(base, glyph_overrides={"ж": {"skeleton_method": "bad"}}), "ж")


def test_invalid_override_field_is_rejected() -> None:
    raw = load_yaml(Path("configs/layout.yaml"))
    raw["centerline"]["glyph_overrides"] = {"ж": {"unknown": 1}}  # type: ignore[index]
    with pytest.raises(ValueError, match="Unknown glyph override"):
        load_centerline_config(raw)
