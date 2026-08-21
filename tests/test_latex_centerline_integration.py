from plotter_processor.latex_renderer import math_renderer_from_options


def test_old_latex_config_uses_centerline_defaults() -> None:
    renderer = math_renderer_from_options({"curve_tolerance_mm": 0.04})

    assert renderer.stroke_mode == "centerline"
    assert renderer.render_ppmm == 24.0
