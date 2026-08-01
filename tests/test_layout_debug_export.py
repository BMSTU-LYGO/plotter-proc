import json
from pathlib import Path

from plotter_processor.layout_debug import export_layout_debug
from plotter_processor.models import PageSpec


def test_layout_debug_exports_overlay_and_machine_readable_placement(tmp_path: Path) -> None:
    placement = {
        "id": "image-1",
        "mapped_bbox_mm": {"x": 10, "y": 20, "width": 30, "height": 20},
        "output_bbox_mm": {"x": 12, "y": 22, "width": 30, "height": 20},
    }
    line = {"page_index": 0, "bbox": {"x": 45, "y": 22, "width": 80, "height": 5}}

    export_layout_debug(tmp_path, PageSpec("A5", 148, 210), [placement], [line])

    payload = json.loads((tmp_path / "placement.json").read_text())
    assert payload["coordinate_unit"] == "mm"
    assert payload["elements"][0]["id"] == "image-1"
    assert "image-1" in (tmp_path / "placement-overlay.svg").read_text()
    assert (tmp_path / "source-layout.svg").is_file()
    assert (tmp_path / "target-layout.svg").is_file()
