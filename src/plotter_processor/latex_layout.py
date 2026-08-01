from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from plotter_processor.font_loader import LoadedFont
from plotter_processor.latex_parser import MathRun, TextRun, parse_latex_runs
from plotter_processor.latex_renderer import (
    MathTextRenderer,
    RenderedMath,
    export_latex_debug,
    scale_rendered_math,
)
from plotter_processor.models import PageSpec, PlotterStroke, Point, PositionedGlyph
from plotter_processor.vector_layout import layout_text


@dataclass(frozen=True, slots=True)
class FormulaInfo:
    formula_index: int
    expression: str
    display_mode: bool
    source_syntax: str
    delimiter: str
    source_position: int
    element_id: str
    width_mm: float
    height_mm: float
    strokes: int
    points: int


@dataclass(slots=True)
class RichLine:
    glyphs: list[PositionedGlyph]
    formula_strokes: list[PlotterStroke]
    height_mm: float
    advance_mm: float
    spacing_before_mm: float
    spacing_after_mm: float
    formula_infos: list[FormulaInfo]
    warnings: list[str]


def layout_latex_paragraph(
    text: str,
    font: LoadedFont,
    usable_width_mm: float,
    size_options: dict[str, object],
    latex_options: dict[str, object],
    renderer: MathTextRenderer,
    *,
    formula_index_start: int,
    element_id: str,
    debug_dir: Path | None = None,
    tab_spaces: int = 4,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
) -> tuple[list[RichLine], int]:
    runs = parse_latex_runs(
        text,
        max_expression_length=_positive_int(latex_options, "max_expression_length"),
        max_elements=_positive_int(latex_options, "max_elements_per_document"),
    )
    em_size = _positive(latex_options if "em_size_mm" in latex_options else size_options, "em_size_mm")
    font_scale = em_size / font.metrics.units_per_em
    ascent = font.metrics.ascent * font_scale
    descent = -font.metrics.descent * font_scale
    standard_height = ascent + descent
    line_multiplier = _positive(size_options, "line_height_multiplier")
    standard_advance = standard_height * line_multiplier
    inline_scale = _positive(latex_options, "inline_size_scale")
    block_scale = _positive(latex_options, "block_size_scale")
    minimum_scale = _positive(latex_options, "min_scale")
    block_before = _non_negative(latex_options, "block_spacing_before_mm")
    block_after = _non_negative(latex_options, "block_spacing_after_mm")
    lines: list[RichLine] = []
    glyphs: list[PositionedGlyph] = []
    formulas: list[tuple[RenderedMath, MathRun, int, float]] = []
    warnings: list[str] = []
    x = 0.0
    formula_index = formula_index_start

    def finish_line(*, before: float = 0.0, after: float = 0.0) -> None:
        nonlocal glyphs, formulas, warnings, x
        if not glyphs and not formulas:
            return
        formula_baseline = max((rendered.baseline_mm for rendered, _, _, _ in formulas), default=0)
        baseline = max(ascent if glyphs else 0.0, formula_baseline)
        below = max(
            descent if glyphs else 0.0,
            max(
                (rendered.height_mm - rendered.baseline_mm for rendered, _, _, _ in formulas),
                default=0.0,
            ),
        )
        height = baseline + below
        placed_glyphs = [replace(glyph, baseline_y_mm=baseline) for glyph in glyphs]
        placed_strokes: list[PlotterStroke] = []
        infos: list[FormulaInfo] = []
        for rendered, run, index, formula_x in formulas:
            formula_id = f"{element_id}-formula-{index:03d}"
            for stroke in rendered.strokes:
                placed_strokes.append(replace(
                    stroke,
                    id=len(placed_strokes),
                    element_id=formula_id,
                    element_type="latex",
                    source_chars=run.expression,
                    points=[
                        Point(
                            point.x + formula_x,
                            point.y + baseline - rendered.baseline_mm,
                        )
                        for point in stroke.points
                    ],
                ))
            infos.append(FormulaInfo(
                index, run.expression, run.display_mode, run.source_syntax, run.delimiter,
                run.start, formula_id, rendered.width_mm, rendered.height_mm,
                len(rendered.strokes), sum(len(stroke.points) for stroke in rendered.strokes),
            ))
        lines.append(RichLine(
            placed_glyphs, placed_strokes, height,
            max(standard_advance, height * line_multiplier), before, after,
            infos, list(dict.fromkeys(warnings)),
        ))
        glyphs, formulas, warnings, x = [], [], [], 0.0

    for run in runs:
        if isinstance(run, TextRun):
            for token in re.split(r"( +)", run.text.replace("\t", " " * tab_spaces)):
                if not token:
                    continue
                if token.isspace():
                    space_width = _space_width(token, font, font_scale)
                    if x > 0 and x + space_width <= usable_width_mm:
                        x += space_width
                    continue
                measured = _layout_word(
                    token, font, em_size, engine=engine, language=language,
                    script=script, direction=direction, features=features,
                )
                clusters = _glyph_clusters(measured)
                word_width = sum(sum(glyph.advance_mm for glyph in cluster) for cluster in clusters)
                if word_width <= usable_width_mm:
                    if x > 0 and x + word_width > usable_width_mm:
                        finish_line()
                    for cluster in clusters:
                        cluster_start = cluster[0].x_mm
                        for glyph in cluster:
                            glyphs.append(
                                replace(glyph, x_mm=x + glyph.x_mm - cluster_start)
                            )
                        x += sum(glyph.advance_mm for glyph in cluster)
                    continue
                warnings.append("forced_word_break")
                for cluster in clusters:
                    cluster_width = sum(glyph.advance_mm for glyph in cluster)
                    if cluster_width > usable_width_mm + 1e-9:
                        raise ValueError(
                            f'Glyph cluster in {token!r} is wider than the usable page width'
                        )
                    if x > 0 and x + cluster_width > usable_width_mm:
                        finish_line()
                    cluster_start = cluster[0].x_mm
                    for glyph in cluster:
                        glyphs.append(replace(glyph, x_mm=x + glyph.x_mm - cluster_start))
                    x += cluster_width
            continue

        formula_index += 1
        size = em_size * (block_scale if run.display_mode else inline_scale)
        try:
            rendered = renderer.render(run.expression, size)
        except ValueError as error:
            raise ValueError(
                f"LaTeX formula {formula_index} in element {element_id!r} "
                f"({run.delimiter}, position {run.start}, backend=mathtext) failed: {error}"
            ) from error
        if rendered.width_mm > usable_width_mm:
            needed_scale = usable_width_mm / rendered.width_mm
            if needed_scale >= minimum_scale:
                rendered = scale_rendered_math(rendered, needed_scale)
                warnings.append(f"latex_formula_scaled: {formula_index}")
            elif not run.display_mode:
                warnings.append(f"inline_formula_moved_to_block: {formula_index}")
                run = replace(run, display_mode=True)
            else:
                raise ValueError(
                    f"LaTeX formula {formula_index} is wider than the page at minimum scale"
                )
        if debug_dir is not None:
            export_latex_debug(
                rendered,
                debug_dir / f"formula-{formula_index:03d}.svg",
                debug_dir / f"formula-{formula_index:03d}.json",
                formula_index=formula_index,
                display_mode=run.display_mode,
                source_syntax=run.source_syntax,
            )
        if run.display_mode:
            finish_line()
            x = (usable_width_mm - rendered.width_mm) / 2
            formulas.append((rendered, run, formula_index, x))
            x += rendered.width_mm
            finish_line(before=block_before, after=block_after)
        else:
            if x > 0 and x + rendered.width_mm > usable_width_mm:
                finish_line()
            formulas.append((rendered, run, formula_index, x))
            x += rendered.width_mm
    finish_line()
    return lines, formula_index


def _layout_word(
    word: str,
    font: LoadedFont,
    em_size_mm: float,
    *,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
) -> list[PositionedGlyph]:
    result = layout_text(
        [word], font, PageSpec("latex-line", 1_000_000.0, 1_000_000.0),
        {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
        {"em_size_mm": em_size_mm, "line_height_multiplier": 1.0, "paragraph_spacing_mm": 0.0},
        engine=engine, language=language, script=script, direction=direction, features=features,
    )
    return result.glyphs


def _glyph_clusters(glyphs: list[PositionedGlyph]) -> list[list[PositionedGlyph]]:
    clusters: list[list[PositionedGlyph]] = []
    for glyph in glyphs:
        if not clusters or clusters[-1][0].cluster_index != glyph.cluster_index:
            clusters.append([glyph])
        else:
            clusters[-1].append(glyph)
    return clusters


def _space_width(text: str, font: LoadedFont, scale: float) -> float:
    try:
        advance = font.advance_for_glyph(font.glyph_name_for_char(" ")) * scale
    except ValueError:
        advance = font.metrics.units_per_em * 0.33 * scale
    return len(text) * advance


def _positive(values: dict[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Missing or invalid positive field: latex.{key}")
    return float(value)


def _non_negative(values: dict[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid non-negative field: latex.{key}")
    return float(value)


def _positive_int(values: dict[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Missing or invalid positive integer field: latex.{key}")
    return value
