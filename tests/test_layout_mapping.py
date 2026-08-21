from plotter_processor.layout_models import RectMM, map_source_rect


def test_preserve_mapping_uses_one_scale_and_centers_source_page() -> None:
    mapped = map_source_rect(
        RectMM(150, 40, 30, 20),
        (210, 297),
        RectMM(12, 12, 124, 178),
    )

    assert mapped.width / mapped.height == 1.5
    assert 12 <= mapped.x < mapped.right <= 136
    assert 12 <= mapped.y < mapped.bottom <= 190


def test_preserve_mapping_does_not_over_upscale() -> None:
    mapped = map_source_rect(RectMM(10, 10, 20, 10), (100, 100), RectMM(0, 0, 500, 500))

    assert mapped.width == 22
    assert mapped.height == 11
