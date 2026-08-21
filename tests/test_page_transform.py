import pytest

from plotter_processor.layout_models import PageTransform, RectMM


@pytest.mark.parametrize(
    ("source_size", "target_size"),
    [
        ((210, 297), (210, 297)),
        ((210, 297), (148, 210)),
        ((148, 210), (148, 210)),
        ((148, 210), (210, 297)),
    ],
)
def test_all_a4_a5_page_combinations_use_uniform_scale(
    source_size: tuple[float, float], target_size: tuple[float, float]
) -> None:
    target = RectMM(10, 10, target_size[0] - 20, target_size[1] - 20)
    transform = PageTransform.create(*source_size, target)
    mapped = transform.map_rect(RectMM(0, 0, *source_size))

    assert mapped.width / mapped.height == pytest.approx(
        source_size[0] / source_size[1]
    )
    assert mapped.width <= target.width + 1e-9
    assert mapped.height <= target.height + 1e-9


def test_a4_to_a5_uses_uniform_content_scale() -> None:
    transform = PageTransform.create(
        210, 297, RectMM(10, 10, 128, 182),
        source_content_rect=RectMM(20, 20, 170, 257),
    )

    assert transform.scale == min(128 / 170, 182 / 257)
    mapped = transform.map_rect(RectMM(40, 50, 80, 40))
    assert mapped.width / mapped.height == 2


def test_a5_to_a4_preserves_aspect_and_center() -> None:
    transform = PageTransform.create(
        148, 210, RectMM(20, 20, 170, 257),
        source_content_rect=RectMM(10, 10, 128, 190),
    )
    mapped = transform.map_rect(RectMM(54, 85, 40, 40))

    assert mapped.width == mapped.height
    assert abs(mapped.center[0] - transform.target_content_rect.center[0]) < 0.01
    assert abs(mapped.center[1] - transform.target_content_rect.center[1]) < 0.01


def test_right_affine_object_and_margins_map_inside_target_content() -> None:
    transform = PageTransform.create(
        210, 297, RectMM(10, 12, 128, 180),
        source_content_rect=RectMM(20, 18, 170, 261),
    )
    mapped = transform.map_rect(RectMM(160, 30, 30, 20))

    mapped_source_content = transform.map_rect(transform.source_content_rect)
    assert mapped.right == pytest.approx(mapped_source_content.right)
    assert mapped.x >= transform.target_content_rect.x
    assert transform.map_relative_x(1.0) == transform.target_content_rect.right
