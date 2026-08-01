from pathlib import Path

import pytest

from plotter_processor.centerline_font.glyph_patch import apply_glyph_patch, load_glyph_patch
from plotter_processor.centerline_font.models import CenterlineGlyph


def _glyph() -> CenterlineGlyph:
    return CenterlineGlyph("ъ", ord("ъ"), "afii10094", 800, ())


def test_replace_patch_validates_sha_and_marks_source(tmp_path: Path) -> None:
    digest = "a" * 64
    path = tmp_path / "patch.yaml"
    path.write_text(
        f'version: 1\nfont_sha256: "{digest}"\nglyphs:\n  "ъ":\n    mode: replace\n'
        "    advance_font_units: 800\n    strokes:\n"
        "      - closed: false\n        points: [[0, 0], [10, 10]]\n",
        encoding="utf-8",
    )
    raw = load_glyph_patch(path, digest)
    patched = apply_glyph_patch(_glyph(), raw["ъ"])
    assert patched.quality["source"] == "manual_patch"
    assert len(patched.strokes) == 1
    with pytest.raises(ValueError, match="does not match"):
        load_glyph_patch(path, "b" * 64)


def test_patch_rejects_non_finite_points() -> None:
    with pytest.raises(ValueError, match="finite"):
        apply_glyph_patch(
            _glyph(),
            {"mode": "replace", "strokes": [{"points": [[0, 0], [float("nan"), 1]]}]},
        )
