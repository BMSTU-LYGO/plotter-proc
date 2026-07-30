from __future__ import annotations

from plotter_processor.centerline_font.models import CenterlineStroke


def pair_strokes_by_tangent(
    strokes: list[CenterlineStroke],
    *,
    tangent_sample_px: int,
    junction_max_angle_deg: float,
) -> list[CenterlineStroke]:
    """Conservative MVP: retain edge strokes when pairing is ambiguous.

    Graph edges never backtrack or duplicate geometry. Pairing remains an
    explicit hook so a future quality-approved implementation can join them.
    """
    del tangent_sample_px, junction_max_angle_deg
    return list(strokes)
