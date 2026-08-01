from pathlib import Path

import pytest

from plotter_processor.svg_importer import import_svg


def _svg(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "x.svg"
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">{body}</svg>')
    return path


def test_imports_basic_shapes_and_nested_transform(tmp_path: Path) -> None:
    path = _svg(tmp_path, '<g transform="translate(1 2)"><line x1="0" y1="0" x2="5" y2="5" stroke="black"/></g>')
    strokes = import_svg(path, x_mm=10, y_mm=20, width_mm=50, height_mm=50)
    assert len(strokes) == 1
    assert strokes[0].points[0] == Point(15, 30)


def test_rejects_script_external_and_text(tmp_path: Path) -> None:
    for body in ('<script/>', '<image href="https://example.com/a.png"/>', '<text>x</text>'):
        with pytest.raises(ValueError, match="Unsafe|unsupported"):
            import_svg(_svg(tmp_path, body), x_mm=0, y_mm=0, width_mm=10, height_mm=10)


from plotter_processor.models import Point
