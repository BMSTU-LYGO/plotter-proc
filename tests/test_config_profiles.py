from pathlib import Path

import yaml

from plotter_processor.config_profiles import resolve_config_profiles


def test_legacy_configs_are_split_into_typed_stage_profiles() -> None:
    layout = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))

    profiles = resolve_config_profiles(layout, machine, page="A5", size="normal")

    assert profiles.paper.name == "A5"
    assert profiles.paper.width_mm == 148
    assert profiles.paper.grid == layout["grid"]
    assert len(profiles.paper.holes) == 2
    assert profiles.paper.hole_clearance_mm == 1.0
    assert profiles.pen.values == machine["pen"]
    assert profiles.machine.feedrate == machine["feedrate_mm_min"]
    assert profiles.handwriting.variation == layout["handwriting"]["variation"]
    assert profiles.handwriting.spacing == layout["handwriting"]["spacing"]
    assert profiles.handwriting.connections == layout["connections"]
    assert profiles.handwriting.stroke_order == layout["handwriting"]["stroke_order"]
    assert profiles.handwriting.routing == layout["handwriting"]["routing"]
    assert profiles.handwriting.retrace == layout["handwriting"]["retrace"]
    assert profiles.conversion.layout == layout["layout"]
    assert "feedrate_mm_min" not in profiles.conversion.layout


def test_page_position_profile_resolves_to_canonical_page_origin() -> None:
    layout = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))

    profiles = resolve_config_profiles(layout, machine, page="A4", size="normal")

    assert profiles.machine.raw["page_origin_mm"] == {"x": 5.0, "y": 5.0}
    assert machine["page_origin_mm"] == {"x": 10.0, "y": 10.0}


def test_legacy_page_origin_remains_supported() -> None:
    layout = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))
    machine.pop("page_position_profiles")
    machine["page_origin_mm"] = {"x": 17.0, "y": 23.0}

    profiles = resolve_config_profiles(layout, machine, page="A5", size="normal")

    assert profiles.machine.raw["page_origin_mm"] == {"x": 17.0, "y": 23.0}
