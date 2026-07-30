from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


@pytest.fixture(scope="session")
def test_font(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("fonts") / "test-vector.ttf"
    characters = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
        "0123456789.,!?:;-—()[]«»\"'№%+=/\\ "
    )
    cmap = {ord(char): f"uni{ord(char):04X}" for char in sorted(characters)}
    cmap[ord(" ")] = "space"
    glyph_order = [
        ".notdef",
        "space",
        *(name for name in dict.fromkeys(cmap.values()) if name != "space"),
    ]
    glyphs = {}
    for name in glyph_order:
        pen = TTGlyphPen(None)
        if name not in {"space", "uni00A0"}:
            pen.moveTo((80, 0))
            pen.lineTo((80, 700))
            pen.qCurveTo((300, 850), (520, 700))
            pen.lineTo((520, 0))
            pen.closePath()
            if name in {"uni041E", "uni043E", "uni0030"}:
                pen.moveTo((200, 200))
                pen.lineTo((400, 200))
                pen.lineTo((400, 600))
                pen.lineTo((200, 600))
                pen.closePath()
        glyphs[name] = pen.glyph()

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(
        {name: (600 if name != "space" else 330, 0) for name in glyph_order}
    )
    builder.setupHorizontalHeader(ascent=800, descent=-200, lineGap=100)
    builder.setupNameTable({"familyName": "Plotter Test", "styleName": "Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, sTypoLineGap=100)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)
    return path
