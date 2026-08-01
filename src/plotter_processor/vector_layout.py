from __future__ import annotations

from collections.abc import Mapping

from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import LayoutResult, PageSpec, PositionedGlyph
from plotter_processor.text_shaper import shape_text_run

OVERFLOW_ERROR = "Text does not fit on one page"


def layout_text(
    paragraphs: list[str],
    font: LoadedFont,
    page: PageSpec,
    margins: Mapping[str, object],
    size_options: Mapping[str, object],
    *,
    tab_spaces: int = 4,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
) -> LayoutResult:
    left = _nonnegative(margins, "left")
    right_margin = _nonnegative(margins, "right")
    top = _nonnegative(margins, "top")
    bottom_margin = _nonnegative(margins, "bottom")
    usable_width = page.width_mm - left - right_margin
    bottom = page.height_mm - bottom_margin
    if usable_width <= 0 or top >= bottom:
        raise ValueError("Page margins leave no usable area")

    em_size = _positive(size_options, "em_size_mm")
    multiplier = _positive(size_options, "line_height_multiplier")
    paragraph_spacing = _nonnegative(size_options, "paragraph_spacing_mm")
    scale = em_size / font.metrics.units_per_em
    line_advance = (
        (font.metrics.ascent - font.metrics.descent + font.metrics.line_gap)
        * scale
        * multiplier
    )
    baseline = top + font.metrics.ascent * scale
    if baseline - font.metrics.descent * scale > bottom:
        raise ValueError(OVERFLOW_ERROR)

    glyphs: list[PositionedGlyph] = []
    glyph_index = 0
    line_index = 0
    max_used_x = left
    word_index = 0
    character_count = sum(len(paragraph) for paragraph in paragraphs)

    def new_line(extra: float = 0.0) -> None:
        nonlocal baseline, line_index
        baseline += line_advance + extra
        line_index += 1
        if baseline - font.metrics.descent * scale > bottom + 1e-9:
            raise ValueError(OVERFLOW_ERROR)

    for paragraph_index, raw_paragraph in enumerate(paragraphs):
        paragraph = raw_paragraph.replace("\t", " " * tab_spaces)
        x = left
        if paragraph:
            tokens = _tokens(paragraph)
            for token, breakable_space in tokens:
                shaped = (
                    shape_text_run(
                        token,
                        font,
                        direction=direction,
                        script=script,
                        language=language,
                        features=features,
                    )
                    if engine == "harfbuzz" and not breakable_space
                    else None
                )
                if engine not in {"legacy", "harfbuzz"}:
                    raise ValueError(f"Unknown layout engine: {engine}")
                token_width = (
                    sum(glyph.x_advance_font_units for glyph in shaped.glyphs) * scale
                    if shaped is not None
                    else _text_advance(token, font, scale)
                )
                if breakable_space:
                    if x > left and x + token_width <= left + usable_width:
                        x += token_width
                    continue
                if x > left and x + token_width > left + usable_width:
                    new_line()
                    x = left
                items = shaped.glyphs if shaped is not None else token
                for item in items:
                    char = item.source_characters if shaped is not None else item
                    glyph_name = (
                        item.glyph_name if shaped is not None else font.glyph_name_for_char(char)
                    )
                    advance = (
                        item.x_advance_font_units * scale
                        if shaped is not None
                        else font.advance_for_glyph(glyph_name) * scale
                    )
                    if x > left and x + advance > left + usable_width:
                        new_line()
                        x = left
                    if x + advance > left + usable_width + 1e-9:
                        raise ValueError(OVERFLOW_ERROR)
                    glyphs.append(
                        PositionedGlyph(
                            char=char,
                            codepoint=ord(char[0]),
                            glyph_name=glyph_name,
                            x_mm=x + (item.x_offset_font_units * scale if shaped is not None else 0),
                            baseline_y_mm=baseline
                            - (item.y_offset_font_units * scale if shaped is not None else 0),
                            advance_mm=advance,
                            scale_mm_per_font_unit=scale,
                            line_index=line_index,
                            glyph_index=glyph_index,
                            word_index=word_index,
                            cluster_index=item.cluster_index if shaped is not None else glyph_index,
                            font_id=item.font.id if shaped is not None else None,
                            font_sha256=item.font.sha256 if shaped is not None else None,
                            x_offset_font_units=(
                                item.x_offset_font_units if shaped is not None else 0.0
                            ),
                            y_offset_font_units=(
                                item.y_offset_font_units if shaped is not None else 0.0
                            ),
                        )
                    )
                    glyph_index += 1
                    x += advance
                    max_used_x = max(max_used_x, x)
                word_index += 1
        if paragraph_index < len(paragraphs) - 1:
            new_line(paragraph_spacing if paragraph else 0.0)

    used_height = max(0.0, baseline - top - font.metrics.descent * scale)
    return LayoutResult(
        glyphs=glyphs,
        warnings=list(font.warnings),
        line_count=line_index + 1,
        character_count=character_count,
        used_width_mm=max_used_x - left,
        used_height_mm=used_height,
    )


def _tokens(text: str) -> list[tuple[str, bool]]:
    tokens: list[tuple[str, bool]] = []
    current = ""
    for char in text:
        if char == " ":
            if current:
                tokens.append((current, False))
                current = ""
            if not tokens or not tokens[-1][1]:
                tokens.append((" ", True))
            else:
                tokens[-1] = (tokens[-1][0] + " ", True)
        else:
            current += char
    if current:
        tokens.append((current, False))
    return tokens


def _text_advance(text: str, font: LoadedFont, scale: float) -> float:
    total = 0.0
    for char in text:
        glyph_name = font.cmap.get(ord(char))
        if glyph_name is None and char == " ":
            total += font.metrics.units_per_em * 0.33 * scale
        elif glyph_name is None:
            font.glyph_name_for_char(char)
        else:
            total += font.advance_for_glyph(glyph_name) * scale
    return total


def _positive(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Missing or invalid positive field: {key}")
    return float(value)


def _nonnegative(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid non-negative field: {key}")
    return float(value)
