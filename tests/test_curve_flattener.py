from plotter_processor.curve_flattener import CurveFlatteningPen


def _quadratic(tolerance: float) -> CurveFlatteningPen:
    pen = CurveFlatteningPen(None, tolerance_mm=tolerance, min_segment_length_mm=0)
    pen.moveTo((0, 0))
    pen.qCurveTo((5, 10), (10, 0))
    pen.closePath()
    return pen


def test_smaller_tolerance_produces_more_points_and_closes_without_duplicate() -> None:
    coarse = _quadratic(2)
    fine = _quadratic(0.05)
    assert len(fine.contours[0].points) > len(coarse.contours[0].points)
    assert fine.contours[0].closed
    assert fine.contours[0].points[0] != fine.contours[0].points[-1]
