import subprocess
from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.cache import default_cache_path, font_sha256
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml


def test_default_cache_is_canonical_and_outside_build(test_font: Path) -> None:
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    digest = font_sha256(test_font)
    target = default_cache_path(digest, config)

    assert config.cache_directory == Path("1-font-cache")
    assert target.parts[0] == "1-font-cache"
    assert target.parts[1] == digest
    assert "build" not in target.parts


def test_cache_directory_does_not_change_config_fingerprint(test_font: Path) -> None:
    from plotter_processor.centerline_font.cache import centerline_config_fingerprint

    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    digest = font_sha256(test_font)
    moved = replace(config, cache_directory=Path("elsewhere"), debug_enabled=not config.debug_enabled)

    assert centerline_config_fingerprint(config, font_hash=digest) == (
        centerline_config_fingerprint(moved, font_hash=digest)
    )


def test_gitignore_contains_persistent_cache() -> None:
    assert "1-font-cache/" in Path(".gitignore").read_text(encoding="utf-8").splitlines()


def test_make_clean_preserves_cache_and_cache_clean_removes_it(tmp_path: Path) -> None:
    build = tmp_path / "build"
    cache = tmp_path / "cache"
    build.mkdir()
    cache.mkdir()
    (build / "job.txt").write_text("job", encoding="utf-8")
    marker = cache / "keep.txt"
    marker.write_text("cache", encoding="utf-8")

    subprocess.run(
        ["make", "clean", f"BUILD={build}", f"CACHE_DIR={cache}"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not (build / "job.txt").exists()
    assert marker.read_text(encoding="utf-8") == "cache"

    subprocess.run(
        [
            "make",
            "cache-clean",
            f"CACHE_DIR={cache}",
            f"FONT_CACHE_DIR={cache / 'font-cache'}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not marker.exists()
    assert (cache / "font-cache").is_dir()
