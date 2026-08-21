from plotter_processor.layout_models import ExclusionZone, RectMM, available_intervals


def test_left_image_leaves_interval_on_right() -> None:
    zone = ExclusionZone(RectMM(10, 20, 40, 30), "both", "image", padding_right_mm=2)

    assert available_intervals(10, 130, 25, 30, [zone]) == [(52, 130)]


def test_right_image_leaves_interval_on_left() -> None:
    zone = ExclusionZone(RectMM(90, 20, 40, 30), "both", "image", padding_left_mm=2)

    assert available_intervals(10, 130, 25, 30, [zone]) == [(10, 88)]


def test_top_bottom_blocks_the_whole_line() -> None:
    zone = ExclusionZone(RectMM(50, 20, 30, 30), "top_bottom", "image")

    assert available_intervals(10, 130, 25, 30, [zone]) == []


def test_zone_above_current_line_no_longer_affects_intervals() -> None:
    zone = ExclusionZone(RectMM(90, 20, 40, 30), "both", "image")

    assert available_intervals(10, 130, 50, 55, [zone]) == [(10, 130)]
