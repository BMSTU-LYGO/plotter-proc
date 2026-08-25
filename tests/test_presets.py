from plotter_processor.presets import resolve_preset


def test_quality_preset_and_explicit_overrides() -> None:
    quality = resolve_preset(
        "quality",
        font_mode=None,
        connections=None,
        workers=None,
        artifact_level=None,
        strict_centerline_quality=False,
    )
    assert quality.font_mode == "centerline"
    assert quality.connections == "safe"
    assert quality.strict_centerline_quality

    explicit = resolve_preset(
        "quality",
        font_mode="outline",
        connections="off",
        workers=2,
        artifact_level="minimal",
        strict_centerline_quality=False,
    )
    assert explicit.font_mode == "outline"
    assert explicit.connections == "off"
    assert explicit.workers == 2
    assert explicit.artifact_level == "minimal"
