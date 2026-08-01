from pathlib import Path

import pytest

from plotter_processor.composition_reader import read_composition


def test_manifest_parses_and_orders_elements(tmp_path: Path) -> None:
    (tmp_path / "font.ttf").touch()
    (tmp_path / "a.svg").write_text("<svg/>")
    manifest = tmp_path / "page.plotter.yaml"
    manifest.write_text(
        "version: 1\npage: A5\nfonts:\n  primary: font.ttf\nelements:\n"
        "  - {id: drawing, type: svg, path: a.svg, x_mm: 1, y_mm: 2, width_mm: 10, height_mm: 10, z_order: 2}\n"
        "  - {id: title, type: text, text: hi, x_mm: 1, y_mm: 2, width_mm: 20, z_order: 1}\n"
    )
    result = read_composition(manifest)
    assert [element.id for element in result.elements] == ["title", "drawing"]


def test_manifest_rejects_duplicate_and_escape(tmp_path: Path) -> None:
    manifest = tmp_path / "page.plotter.yaml"
    manifest.write_text(
        "version: 1\npage: A5\nfonts:\n  primary: ../font.ttf\n"
        "elements:\n  - {id: x, type: svg, path: ../bad.svg, x_mm: 0, y_mm: 0, width_mm: 10, height_mm: 10}\n"
    )
    with pytest.raises(ValueError, match="escapes"):
        read_composition(manifest)
