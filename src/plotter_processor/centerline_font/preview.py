from __future__ import annotations

import html
from pathlib import Path

from plotter_processor.centerline_font.models import CompiledCenterlineFont


def export_centerline_font_preview(
    font: CompiledCenterlineFont, glyph_names: list[str], output_path: Path
) -> None:
    selected = [font.glyphs[char] for char in glyph_names if char in font.glyphs]
    cell_w, cell_h, columns = 260, 280, 5
    rows = max(1, (len(selected) + columns - 1) // columns)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{cell_w * columns}" '
            f'height="{cell_h * rows}" viewBox="0 0 {cell_w * columns} {cell_h * rows}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    scale = 0.16
    for index, glyph in enumerate(selected):
        ox = (index % columns) * cell_w + 20
        oy = (index // columns) * cell_h + 210
        parts.append(f'<line x1="{ox}" y1="{oy}" x2="{ox + glyph.advance_font_units * scale}" y2="{oy}" stroke="#aac"/>')
        color = "#c22" if glyph.quality.get("needs_review") else "#111"
        for stroke in glyph.strokes:
            points = " ".join(
                f"{ox + p.x * scale:.2f},{oy - p.y * scale:.2f}" for p in stroke.points
            )
            tag = "polygon" if stroke.closed else "polyline"
            parts.append(
                f'<{tag} points="{points}" fill="none" stroke="{color}" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
            )
        total_points = sum(len(stroke.points) for stroke in glyph.strokes)
        retrace = float(glyph.quality.get("retrace_ratio", 0.0)) * 100
        parts.append(
            f'<text x="{ox}" y="{oy + 26}" font-family="sans-serif" font-size="14">'
            f'{html.escape(glyph.char)} · {html.escape(glyph.glyph_name)} · '
            f'components={len(glyph.strokes)} strokes={len(glyph.strokes)} '
            f'retrace={retrace:.1f}% · {total_points} points</text>'
        )
    parts.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
