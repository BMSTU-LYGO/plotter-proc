from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.cache import (
    centerline_config_fingerprint,
    default_cache_path,
    font_sha256,
)
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml


def _config():
    return load_centerline_config(load_yaml(Path("configs/layout.yaml")))


def test_font_sha_is_part_of_cache_identity(test_font: Path) -> None:
    config = _config()
    first = default_cache_path(font_sha256(test_font), config)
    second = default_cache_path(font_sha256(Path("assets/1.ttf")), config)

    assert first.parent.parent != second.parent.parent


def test_algorithm_version_invalidates_cache(test_font: Path) -> None:
    config = _config()
    digest = font_sha256(test_font)

    assert default_cache_path(digest, config) != default_cache_path(
        digest, replace(config, algorithm_version=config.algorithm_version + 1)
    )


def test_relevant_centerline_setting_invalidates_cache(test_font: Path) -> None:
    config = _config()
    digest = font_sha256(test_font)

    assert centerline_config_fingerprint(config, font_hash=digest) != (
        centerline_config_fingerprint(
            replace(config, threshold=config.threshold - 1), font_hash=digest
        )
    )


def test_page_and_machine_settings_do_not_invalidate_cache(test_font: Path) -> None:
    first = load_yaml(Path("configs/layout.yaml"))
    second = load_yaml(Path("configs/layout.yaml"))
    second["pages"]["A5"]["width_mm"] = 999
    second["margins_mm"]["left"] = 33
    digest = font_sha256(test_font)

    assert centerline_config_fingerprint(
        load_centerline_config(first), font_hash=digest
    ) == centerline_config_fingerprint(load_centerline_config(second), font_hash=digest)
    # Machine/G-code configuration is never an input of the centerline fingerprint API.
    assert "machine" not in centerline_config_fingerprint.__annotations__

