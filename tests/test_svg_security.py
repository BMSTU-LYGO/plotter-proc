from pathlib import Path

import pytest

from plotter_processor.svg_importer import import_svg


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "unsafe.svg"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "body,match",
    [
        ('<script>alert(1)</script>', "Unsafe"),
        ('<image href="file:///etc/passwd"/>', "Unsafe"),
        ('<text>hello</text>', "unsupported"),
        ('<line onload="x()" x1="0" y1="0" x2="1" y2="1"/>', "Unsafe"),
        ('<g transform="skewX(2)"><line x1="0" y1="0" x2="1" y2="1"/></g>', "transform"),
    ],
)
def test_unsafe_features_are_rejected(tmp_path: Path, body: str, match: str) -> None:
    path = _write(tmp_path, f'<svg viewBox="0 0 10 10">{body}</svg>')
    with pytest.raises(ValueError, match=match):
        import_svg(path, x_mm=0, y_mm=0, width_mm=10, height_mm=10)


def test_entities_empty_and_missing_dimensions_are_rejected(tmp_path: Path) -> None:
    entity = _write(tmp_path, '<!DOCTYPE svg [<!ENTITY x "boom">]><svg viewBox="0 0 1 1"/>')
    with pytest.raises(ValueError, match="DOCTYPE"):
        import_svg(entity, x_mm=0, y_mm=0, width_mm=1, height_mm=1)
    empty = _write(tmp_path, '<svg viewBox="0 0 1 1"/>')
    with pytest.raises(ValueError, match="no supported"):
        import_svg(empty, x_mm=0, y_mm=0, width_mm=1, height_mm=1)
    missing = _write(tmp_path, '<svg><line x1="0" y1="0" x2="1" y2="1"/></svg>')
    with pytest.raises(ValueError, match="viewBox"):
        import_svg(missing, x_mm=0, y_mm=0, width_mm=1, height_mm=1)


def test_file_and_point_limits_are_enforced(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '<svg viewBox="0 0 10 10"><line x1="0" y1="0" x2="1" y2="1"/></svg>',
    )
    with pytest.raises(ValueError, match="file size"):
        import_svg(path, x_mm=0, y_mm=0, width_mm=1, height_mm=1, max_file_bytes=5)
    with pytest.raises(ValueError, match="point limit"):
        import_svg(path, x_mm=0, y_mm=0, width_mm=1, height_mm=1, max_points=1)
