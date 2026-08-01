from plotter_processor.centerline_font.visual_regression import compare_snapshots


def test_geometry_comparison_uses_tolerance_friendly_distance() -> None:
    left = {
        "stroke_count": 1,
        "point_count": 2,
        "bbox": [0, 0, 10, 0],
        "sampled_points": [[0, 0], [10, 0]],
    }
    right = {
        "stroke_count": 1,
        "point_count": 2,
        "bbox": [0, 0.1, 10, 0.1],
        "sampled_points": [[0, 0.1], [10, 0.1]],
    }
    result = compare_snapshots(left, right)
    assert result.stroke_count_delta == 0
    assert result.bbox_delta == 0.1
    assert result.hausdorff_distance == 0.1
