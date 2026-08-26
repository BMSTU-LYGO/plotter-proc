from pathlib import Path

import pytest

from plotter_processor.cli import build_parser
from tools.run_with_config import build_run_arguments


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (
            "super-fast",
            {
                "preset": "fast",
                "motion_profile": "fast",
                "connections": "aggressive",
                "join_writing": True,
                "font_mode": "centerline",
                "artifacts": "minimal",
            },
        ),
        (
            "balanced",
            {
                "motion_profile": "balanced",
                "connections": "safe",
                "join_writing": True,
                "artifacts": "normal",
            },
        ),
        (
            "quality",
            {
                "preset": "quality",
                "motion_profile": "safe",
                "connections": "safe",
                "strict_centerline_quality": True,
                "strict_latex_quality": True,
                "artifacts": "audit",
            },
        ),
    ],
)
def test_run_profiles_expand_to_valid_cli_flags(
    profile: str, expected: dict[str, object]
) -> None:
    arguments = build_run_arguments(
        Path("configs/run_conf.yaml"),
        profile,
        input_path=Path("document.txt"),
        font_path=Path("font.ttf"),
        build_root=Path("custom-build"),
    )
    parsed = build_parser().parse_args(arguments)

    for name, value in expected.items():
        assert getattr(parsed, name) == value
    assert parsed.output_dir == Path("custom-build") / profile
    assert parsed.stage_cache == Path("custom-build") / profile / ".stage-cache"


def test_unknown_run_profile_has_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown run profile"):
        build_run_arguments(
            Path("configs/run_conf.yaml"),
            "missing",
            input_path=Path("document.txt"),
            font_path=Path("font.ttf"),
            build_root=Path("build"),
        )
