from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from plotter_processor.document_models import SourceParagraph, SourceTabStop
from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import PositionedGlyph
from plotter_processor.text_shaper import shape_text_run

_SEPARATE_PUNCTUATION = frozenset(".,:;!?")


@dataclass(frozen=True, slots=True)
class ParagraphLine:
    glyphs: tuple[PositionedGlyph, ...]
    left_mm: float
    right_mm: float
    used_left_mm: float
    used_right_mm: float
    advance_mm: float
    is_last: bool


@dataclass(frozen=True, slots=True)
class ParagraphLayout:
    lines: tuple[ParagraphLine, ...]
    font_scale: float
    space_before_mm: float
    space_after_mm: float
    tab_stops_mm: tuple[float, ...]


@dataclass(slots=True)
class _MutableLine:
    glyphs: list[PositionedGlyph]
    left: float
    right: float
    cursor: float
    word_count: int = 0
    has_tab: bool = False


def layout_paragraph(
    paragraph: SourceParagraph,
    font: LoadedFont,
    *,
    content_left_mm: float,
    content_right_mm: float,
    base_size_options: Mapping[str, object],
    paragraph_options: Mapping[str, object],
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
    tab_scale: float = 1.0,
) -> ParagraphLayout:
    if tab_scale <= 0:
        raise ValueError("tab_scale must be positive")
    role = paragraph.semantic_role or "body"
    font_scale = _font_scale(paragraph, paragraph_options, role)
    em_size = float(base_size_options["em_size_mm"]) * font_scale
    scale = em_size / font.metrics.units_per_em
    multiplier = paragraph.line_spacing or float(base_size_options["line_height_multiplier"])
    line_advance = (
        (font.metrics.ascent - font.metrics.descent + font.metrics.line_gap)
        * scale
        * multiplier
    )
    grid_width = _optional_positive(paragraph_options, "grid_cell_width_mm")
    configured_indent = _cells(paragraph_options, "indent_cells", grid_width)
    configured_first_indent = _cells(
        paragraph_options, "first_line_indent_cells", grid_width
    )
    left_indent = max(
        0.0,
        paragraph.left_indent_mm
        if paragraph.left_indent_mm is not None
        else configured_indent,
    )
    right_indent = max(0.0, paragraph.right_indent_mm or 0.0)
    paragraph_left = content_left_mm + left_indent
    paragraph_right = content_right_mm - right_indent
    first_left = paragraph_left + (
        paragraph.first_line_indent_mm
        if paragraph.first_line_indent_mm is not None
        else configured_first_indent
    )
    first_left -= paragraph.hanging_indent_mm or 0.0
    first_left = max(content_left_mm, first_left)
    if paragraph_right <= max(paragraph_left, first_left):
        raise ValueError("Paragraph indents leave no usable line width")

    interval = _cells(paragraph_options, "tab_interval_cells", grid_width) or float(
        paragraph_options.get("default_tab_interval_mm", 12.5)
    )
    if interval <= 0:
        raise ValueError("paragraphs.default_tab_interval_mm must be positive")
    source_stops = paragraph.tab_stops or tuple(
        SourceTabStop(position) for position in paragraph.tab_stops_mm
    )
    custom_stops = tuple(
        SourceTabStop(paragraph_left + stop.position_mm * tab_scale, stop.alignment)
        for stop in source_stops
        if stop.position_mm > 0
    )
    lines: list[_MutableLine] = []

    def new_line() -> _MutableLine:
        line_left = first_left if not lines else paragraph_left
        line = _MutableLine([], line_left, paragraph_right, line_left)
        lines.append(line)
        return line

    line = new_line()
    pending_space = 0.0
    space_width = _advance(" ", font, scale)
    tokens = _tokens(paragraph.text)
    for token_index, (kind, value) in enumerate(tokens):
        if kind == "space":
            pending_space = min(
                pending_space + len(value) * space_width,
                space_width * _word_space_factor(paragraph_options),
            )
            continue
        if kind == "tab":
            following = next(
                (token for token_kind, token in tokens[token_index + 1 :] if token_kind == "word"),
                "",
            )
            line.cursor = _next_tab_stop(
                line.cursor,
                paragraph_left,
                custom_stops,
                interval,
                following,
                font,
                scale,
                engine,
                language,
                script,
                direction,
                features,
            )
            line.has_tab = True
            pending_space = 0.0
            if line.cursor >= line.right - 1e-9:
                line = new_line()
            continue

        remaining = value
        while remaining:
            word_width = _advance(remaining, font, scale, engine, language, script, direction, features)
            proposed = line.cursor + (pending_space if line.word_count else 0.0)
            if line.word_count and proposed + word_width > line.right + 1e-9:
                line = new_line()
                pending_space = 0.0
                continue
            if proposed + word_width > line.right + 1e-9:
                head, tail = _split_word(
                    remaining,
                    line.right - proposed,
                    font,
                    scale,
                    engine,
                    language,
                    script,
                    direction,
                    features,
                )
                if not head and line.word_count:
                    line = new_line()
                    pending_space = 0.0
                    continue
                head = head or remaining[:1]
                tail = tail if head != remaining[:1] or len(remaining) == 1 else remaining[1:]
                line.cursor = proposed
                _append_word(
                    line, head, font, scale, engine, language, script, direction, features,
                    paragraph_options,
                )
                remaining = tail
                pending_space = 0.0
                if remaining:
                    line = new_line()
                continue
            line.cursor = proposed
            _append_word(
                line, remaining, font, scale, engine, language, script, direction, features,
                paragraph_options,
            )
            remaining = ""
            pending_space = 0.0

    alignment = paragraph.alignment or "left"
    rendered: list[ParagraphLine] = []
    for index, item in enumerate(lines):
        last = index == len(lines) - 1
        used = max(0.0, item.cursor - item.left)
        glyphs = list(item.glyphs)
        if alignment == "center":
            shift = max(0.0, (item.right - item.left - used) / 2.0)
            glyphs = [replace(glyph, x_mm=glyph.x_mm + shift) for glyph in glyphs]
        elif alignment == "right":
            shift = max(0.0, item.right - item.left - used)
            glyphs = [replace(glyph, x_mm=glyph.x_mm + shift) for glyph in glyphs]
        elif (
            alignment == "justify"
            and not last
            and role not in {"title", "heading_1", "heading_2", "heading_3"}
            and item.word_count > 1
            and not item.has_tab
        ):
            gaps = item.word_count - 1
            extra = min(
                max(0.0, item.right - item.left - used) / gaps,
                float(paragraph_options.get("max_extra_space_per_word_mm", 4.0)),
            )
            glyphs = [
                replace(glyph, x_mm=glyph.x_mm + max(0, glyph.word_index) * extra)
                for glyph in glyphs
            ]
        used_left = min((glyph.x_mm for glyph in glyphs), default=item.left)
        used_right = max(
            (glyph.x_mm + glyph.advance_mm for glyph in glyphs), default=used_left
        )
        rendered.append(ParagraphLine(
            tuple(glyphs), item.left, item.right, used_left, used_right, line_advance, last
        ))

    maximum_before = float(paragraph_options.get("max_space_before_mm", 12.0))
    maximum_after = float(paragraph_options.get("max_space_after_mm", 12.0))
    return ParagraphLayout(
        tuple(rendered),
        font_scale,
        min(maximum_before, max(0.0, paragraph.space_before_mm or 0.0)),
        min(maximum_after, max(0.0, paragraph.space_after_mm or 0.0)),
        tuple(stop.position_mm for stop in custom_stops),
    )


def _font_scale(
    paragraph: SourceParagraph, options: Mapping[str, object], role: str
) -> float:
    semantic = options.get("semantic_scale", {})
    semantic_scale = (
        float(semantic.get(role, semantic.get("body", 1.0)))
        if isinstance(semantic, Mapping)
        else 1.0
    )
    source_sizes = [
        run.style.font_size_pt
        for run in paragraph.runs
        if run.style.font_size_pt is not None and run.text.strip()
    ]
    if bool(options.get("preserve_relative_font_size", True)) and source_sizes:
        semantic_scale = sum(source_sizes) / len(source_sizes) / float(
            options.get("source_body_font_size_pt", 12.0)
        )
    return min(
        float(options.get("max_font_scale", 1.60)),
        max(float(options.get("min_font_scale", 0.80)), semantic_scale),
    )


def _optional_positive(values: Mapping[str, object], key: str) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"paragraphs.{key} must be positive")
    return float(value)


def _cells(
    values: Mapping[str, object], key: str, cell_width_mm: float | None
) -> float:
    value = values.get(key)
    if value is None:
        return 0.0
    if cell_width_mm is None:
        raise ValueError(f"paragraphs.{key} requires an enabled page grid")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"paragraphs.{key} must be non-negative")
    return float(value) * cell_width_mm


def _tokens(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    current = ""
    current_kind = ""
    for char in text:
        kind = "tab" if char == "\t" else "space" if char.isspace() else "word"
        if kind == "tab":
            if current:
                tokens.append((current_kind, current))
                current = ""
            tokens.append((kind, char))
            current_kind = ""
        elif kind == current_kind:
            current += char
        else:
            if current:
                tokens.append((current_kind, current))
            current_kind = kind
            current = char
    if current:
        tokens.append((current_kind, current))
    return tokens


def _next_tab_stop(
    current: float,
    paragraph_left: float,
    custom_stops: tuple[SourceTabStop, ...],
    interval: float,
    following: str,
    font: LoadedFont,
    scale: float,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
) -> float:
    for stop in custom_stops:
        if stop.position_mm <= current + 1e-9:
            continue
        width = _advance(
            following, font, scale, engine, language, script, direction, features
        )
        if stop.alignment == "left":
            return stop.position_mm
        if stop.alignment == "center":
            return stop.position_mm - width / 2
        if stop.alignment == "right":
            return stop.position_mm - width
        if stop.alignment == "decimal":
            separators = [
                index for index, char in enumerate(following) if char in {".", ","}
            ]
            prefix = following[: separators[0]] if separators else following
            return stop.position_mm - _advance(
                prefix, font, scale, engine, language, script, direction, features
            )
        raise ValueError(f"Unknown tab alignment: {stop.alignment}")
    steps = int(max(0.0, current - paragraph_left) // interval) + 1
    return paragraph_left + steps * interval


def _split_word(
    text: str,
    width: float,
    font: LoadedFont,
    scale: float,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
) -> tuple[str, str]:
    split = 0
    for index in range(1, len(text) + 1):
        if _advance(
            text[:index], font, scale, engine, language, script, direction, features
        ) > width + 1e-9:
            break
        split = index
    return text[:split], text[split:]


def _append_word(
    line: _MutableLine,
    text: str,
    font: LoadedFont,
    scale: float,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
    paragraph_options: Mapping[str, object] | None = None,
) -> None:
    options = paragraph_options or {}
    word_index = line.word_count
    if engine == "harfbuzz":
        shaped = shape_text_run(
            text,
            font,
            direction=direction,
            script=script,
            language=language,
            features=features,
        )
        for item in shaped.glyphs:
            advance = item.x_advance_font_units * scale
            text_role = _text_role(item.source_characters)
            gap = _punctuation_gap(line, item.source_characters, text_role, options)
            line.cursor += gap
            line.glyphs.append(PositionedGlyph(
                char=item.source_characters,
                codepoint=ord(item.source_characters[0]),
                glyph_name=item.glyph_name,
                x_mm=line.cursor + item.x_offset_font_units * scale,
                baseline_y_mm=_punctuation_vertical_offset(text_role, options),
                advance_mm=advance,
                scale_mm_per_font_unit=scale,
                line_index=0,
                glyph_index=len(line.glyphs),
                word_index=word_index,
                cluster_index=item.cluster_index,
                font_id=item.font.id,
                font_sha256=item.font.sha256,
                x_offset_font_units=item.x_offset_font_units,
                y_offset_font_units=item.y_offset_font_units,
                text_role=text_role,
            ))
            line.cursor += advance
    elif engine == "legacy":
        for character in text:
            glyph_name = font.glyph_name_for_char(character)
            advance = font.advance_for_glyph(glyph_name) * scale
            text_role = _text_role(character)
            gap = _punctuation_gap(line, character, text_role, options)
            line.cursor += gap
            line.glyphs.append(PositionedGlyph(
                char=character,
                codepoint=ord(character),
                glyph_name=glyph_name,
                x_mm=line.cursor,
                baseline_y_mm=_punctuation_vertical_offset(text_role, options),
                advance_mm=advance,
                scale_mm_per_font_unit=scale,
                line_index=0,
                glyph_index=len(line.glyphs),
                word_index=word_index,
                cluster_index=len(line.glyphs),
                text_role=text_role,
            ))
            line.cursor += advance
    else:
        raise ValueError(f"Unknown layout engine: {engine}")
    line.word_count += 1


def _advance(
    text: str,
    font: LoadedFont,
    scale: float,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
) -> float:
    if engine == "harfbuzz" and text.strip():
        return sum(
            glyph.x_advance_font_units
            for glyph in shape_text_run(
                text,
                font,
                direction=direction,
                script=script,
                language=language,
                features=features,
            ).glyphs
        ) * scale
    total = 0.0
    for character in text:
        glyph_name = font.cmap.get(ord(character))
        if glyph_name is None and character.isspace():
            total += font.metrics.units_per_em * 0.33 * scale
        else:
            glyph_name = font.glyph_name_for_char(character)
            total += font.advance_for_glyph(glyph_name) * scale
    return total


def _word_space_factor(values: Mapping[str, object]) -> float:
    value = values.get("max_word_space_factor", 1.5)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 1.0 <= value <= 2.0
    ):
        raise ValueError("paragraphs.max_word_space_factor must be between 1.0 and 2.0")
    return float(value)


def _text_role(text: str) -> str:
    return "punctuation" if text and all(char in _SEPARATE_PUNCTUATION for char in text) else "letter"


def _punctuation_gap(
    line: _MutableLine,
    text: str,
    text_role: str,
    values: Mapping[str, object],
) -> float:
    if text_role != "punctuation" or not line.glyphs or line.glyphs[-1].text_role != "letter":
        return 0.0
    if text in {".", ","} and line.glyphs[-1].char[-1:].isdigit():
        return 0.0
    return _punctuation_value(values, "punctuation_gap_mm", 0.25)


def _punctuation_vertical_offset(
    text_role: str, values: Mapping[str, object]
) -> float:
    if text_role != "punctuation":
        return 0.0
    return _punctuation_value(values, "punctuation_vertical_offset_mm", 0.0)


def _punctuation_value(
    values: Mapping[str, object], key: str, default: float
) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value) > 2:
        raise ValueError(f"Invalid punctuation layout value: {key}")
    return float(value)
