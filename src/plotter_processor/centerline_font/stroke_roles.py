from __future__ import annotations

from dataclasses import dataclass

from plotter_processor.models import PlotterStroke


@dataclass(frozen=True, slots=True)
class ClassifiedStrokes:
    main: PlotterStroke | None
    secondary: tuple[PlotterStroke, ...]
    diacritics: tuple[PlotterStroke, ...]
    confidence: float


def classify_strokes(strokes: list[PlotterStroke], baseline_y: float) -> ClassifiedStrokes:
    if not strokes:
        return ClassifiedStrokes(None, (), (), 0.0)
    lengths = {stroke.id: _length(stroke) for stroke in strokes}
    open_strokes = [stroke for stroke in strokes if not stroke.closed]
    candidates = open_strokes or strokes
    main = max(
        candidates,
        key=lambda stroke: (
            lengths[stroke.id],
            max(point.x for point in stroke.points) - min(point.x for point in stroke.points),
            -stroke.id,
        ),
    )
    threshold = lengths[main.id] * 0.25
    diacritics = tuple(
        stroke
        for stroke in strokes
        if stroke is not main
        and lengths[stroke.id] < threshold
        and max(point.y for point in stroke.points) < baseline_y
    )
    secondary = tuple(stroke for stroke in strokes if stroke is not main and stroke not in diacritics)
    total = sum(lengths.values())
    confidence = lengths[main.id] / total if total else 0.0
    return ClassifiedStrokes(main, secondary, diacritics, round(confidence, 6))


def _length(stroke: PlotterStroke) -> float:
    return sum(
        ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5
        for a, b in zip(stroke.points, stroke.points[1:])
    )
