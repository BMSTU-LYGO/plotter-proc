from __future__ import annotations

from collections import defaultdict

from plotter_processor.document_models import SourceParagraph
from plotter_processor.models import PlotterStroke, Point, PositionedGlyph


def build_underlines(
    paragraph: SourceParagraph,
    glyphs: list[PositionedGlyph],
    *,
    element_id: str,
    em_size_mm: float,
    offset_em: float = 0.12,
    double_gap_mm: float = 0.45,
    min_length_mm: float = 0.5,
) -> list[PlotterStroke]:
    result: list[PlotterStroke] = []
    cursor = 0
    for run_index, run in enumerate(paragraph.runs):
        run_glyphs = glyphs[cursor : cursor + len(run.text)]
        cursor += len(run.text)
        if not run.text or run.style.underline is None:
            continue
        groups: dict[int, list[PositionedGlyph]] = defaultdict(list)
        for glyph, character in zip(run_glyphs, run.text, strict=False):
            if run.style.underline == "words" and character.isspace():
                continue
            groups[glyph.line_index].append(glyph)
        for group_index, group in enumerate(groups.values()):
            for word_group in _contiguous(group, run.style.underline == "words"):
                start = min(glyph.x_mm for glyph in word_group)
                end = max(glyph.x_mm + glyph.advance_mm for glyph in word_group)
                if end - start < min_length_mm:
                    continue
                baseline = word_group[0].baseline_y_mm
                y = baseline + em_size_mm * offset_em
                lines = 2 if run.style.underline == "double" else 1
                for line_index in range(lines):
                    result.append(PlotterStroke(
                        len(result),
                        [Point(start, y + line_index * double_gap_mm), Point(end, y + line_index * double_gap_mm)],
                        False,
                        element_id=f"{element_id}-underline-{run_index + 1}-{group_index + 1}",
                        element_type="text-decoration",
                        semantic_role="underline",
                        segment_types=("underline",),
                        preserve_order=True,
                        z_order=20,
                    ))
    return result


def _contiguous(
    glyphs: list[PositionedGlyph], words_only: bool
) -> list[list[PositionedGlyph]]:
    if not words_only or not glyphs:
        return [glyphs] if glyphs else []
    result: list[list[PositionedGlyph]] = [[glyphs[0]]]
    for glyph in glyphs[1:]:
        previous = result[-1][-1]
        if glyph.x_mm - (previous.x_mm + previous.advance_mm) > previous.advance_mm * 0.8:
            result.append([])
        result[-1].append(glyph)
    return result
