from __future__ import annotations

from pathlib import Path

from plotter_processor.centerline_font.cache import font_sha256
from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import FontIdentity, ShapedGlyph, ShapedRun


def shape_text_run(
    text: str,
    font: LoadedFont,
    *,
    direction: str = "ltr",
    script: str = "Cyrl",
    language: str = "ru",
    features: tuple[str, ...] = (),
) -> ShapedRun:
    try:
        import uharfbuzz as hb
    except ImportError as error:
        raise RuntimeError(
            "HarfBuzz layout requires the 'uharfbuzz' dependency; use layout.engine=legacy "
            "or install the project dependencies"
        ) from error
    source = Path(font.path)
    identity = FontIdentity(source.stem, source, font_sha256(source))
    blob = source.read_bytes()
    face = hb.Face(blob)
    hb_font = hb.Font(face)
    hb_font.scale = (font.metrics.units_per_em, font.metrics.units_per_em)
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.direction = direction
    buffer.script = script
    buffer.language = language
    hb.shape(hb_font, buffer, dict.fromkeys(features, 1))
    infos = buffer.glyph_infos
    positions = buffer.glyph_positions
    glyph_order = font.font.getGlyphOrder()
    clusters = [info.cluster for info in infos] + [len(text)]
    shaped: list[ShapedGlyph] = []
    for index, (info, position) in enumerate(zip(infos, positions, strict=True)):
        start = info.cluster
        later = [cluster for cluster in clusters[index + 1 :] if cluster > start]
        end = min(later, default=len(text))
        shaped.append(
            ShapedGlyph(
                text[start:end] or text[start : start + 1],
                info.codepoint,
                glyph_order[info.codepoint],
                identity,
                start,
                position.x_advance,
                position.y_advance,
                position.x_offset,
                position.y_offset,
            )
        )
    return ShapedRun(text, tuple(shaped), direction, script, language)
