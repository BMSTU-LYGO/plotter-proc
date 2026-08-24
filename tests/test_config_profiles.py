from pathlib import Path

import yaml

from plotter_processor.config_profiles import resolve_config_profiles


def test_legacy_configs_are_split_into_typed_stage_profiles() -> None:
    layout = yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))
    machine = yaml.safe_load(Path("configs/machine.yaml").read_text(encoding="utf-8"))

    profiles = resolve_config_profiles(layout, machine, page="A5", size="normal")

    assert profiles.paper.name == "A5"
    assert profiles.paper.width_mm == 148
    assert profiles.pen.values == machine["pen"]
    assert profiles.machine.feedrate == machine["feedrate_mm_min"]
    assert profiles.handwriting.variation == layout["handwriting"]["variation"]
    assert profiles.conversion.layout == layout["layout"]
    assert "feedrate_mm_min" not in profiles.conversion.layout
