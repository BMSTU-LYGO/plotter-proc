import pytest

from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.validator import validate_path_document


def test_rejects_non_finite_and_page_overflow() -> None:
    invalid = PathDocument(
        10,
        10,
        [PlotterStroke(0, [Point(1, 1), Point(11, 2)], False)],
        [],
    )
    with pytest.raises(ValueError, match="outside the page"):
        validate_path_document(invalid, max_points_per_contour=10)

    invalid.strokes[0].points[1] = Point(float("nan"), 2)
    with pytest.raises(ValueError, match="non-finite"):
        validate_path_document(invalid, max_points_per_contour=10)
