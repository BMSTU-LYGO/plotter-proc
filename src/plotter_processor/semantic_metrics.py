from __future__ import annotations


def semantic_report(strokes: list[object]) -> dict[str, object]:
    """Measure conflicting classifications on identical geometric primitives."""
    classifications: dict[tuple[tuple[float, float], ...], set[str]] = {}
    for stroke in strokes:
        role = getattr(stroke, "semantic_role", None)
        points = getattr(stroke, "points", ())
        if not role or len(points) < 2:
            continue
        forward = tuple((round(point.x, 6), round(point.y, 6)) for point in points)
        reverse = tuple(reversed(forward))
        key = min(forward, reverse)
        classifications.setdefault(key, set()).add(str(role))
    conflicts = sum(max(0, len(roles) - 1) for roles in classifications.values())
    return {
        "classification_conflicts": conflicts,
        "classification_conflicts_measured": True,
        # No semantic primitive suppression pass exists today. Null is intentional:
        # it must not be confused with a measured zero.
        "duplicate_primitives_suppressed": None,
        "duplicate_primitives_suppressed_measured": False,
    }
