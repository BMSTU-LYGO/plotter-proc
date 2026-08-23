import json
from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml


def test_debug_export_has_stable_complete_artifact_set(tmp_path: Path) -> None:
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    config = replace(config, em_resolution_px=96, padding_px=4, font_overrides={})
    font = Path("assets/1.ttf")
    compile_centerline_font(
        font,
        {"ь"},
        config,
        cache_path=tmp_path / "font.json",
        force=True,
        debug_dir=tmp_path / "debug",
    )
    target = tmp_path / "debug" / "U+044C-ь"
    expected = {
        "00_raster.png",
        "01_mask.png",
        "02_distance.png",
        "03_skeleton_skeletonize.png",
        "04_skeleton_medial_axis.png",
        "05_selected_skeleton.png",
        "06_graph_nodes_edges.svg",
        "07_routes.svg",
        "08_smoothed_strokes.svg",
        "09_reconstructed_mask.png",
        "10_mask_difference.png",
        "11_overlay.svg",
        "metrics.json",
    }
    assert expected <= {path.name for path in target.iterdir()}
    for svg in target.glob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        assert "nan" not in text.lower()
        assert "infinity" not in text.lower()
    metrics = json.loads((target / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["short_edges"] >= 0
    assert metrics["micro_loops"] >= 0
    assert metrics["minimum_one_route_retrace_length"] >= 0
    assert metrics["excess_retrace_length"] == 0


def test_debug_export_does_not_change_compiled_geometry(tmp_path: Path) -> None:
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    config = replace(config, em_resolution_px=96, padding_px=4, font_overrides={})
    plain, _ = compile_centerline_font(
        Path("assets/1.ttf"), {"ь"}, config, cache_path=tmp_path / "plain.json", force=True
    )
    debug, _ = compile_centerline_font(
        Path("assets/1.ttf"),
        {"ь"},
        config,
        cache_path=tmp_path / "debug.json",
        force=True,
        debug_dir=tmp_path / "debug",
    )
    assert plain.glyphs["ь"].strokes == debug.glyphs["ь"].strokes
