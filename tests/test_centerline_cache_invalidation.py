from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from plotter_processor.centerline_font import compiler
from plotter_processor.centerline_font.cache import (
    cache_status,
    default_cache_path,
    font_sha256,
    glyph_shard_path,
    metadata_path,
    shard_manifest_path,
)
from plotter_processor.centerline_font.compiler import (
    compile_centerline_font,
    resolve_centerline_worker_count,
)
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.models import CenterlineGlyph, CenterlineStroke
from plotter_processor.centerline_font.serializer import write_centerline_font_atomic
from plotter_processor.config import load_yaml
from plotter_processor.models import Point


def _config(tmp_path: Path):
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    return replace(
        config,
        cache_directory=tmp_path / "font-cache",
        font_overrides={},
        glyph_overrides={},
        glyph_patch_file=None,
    )


def _fake_glyph(_source, char, _font, _config, _debug, _digest, _fingerprint=None):
    return CenterlineGlyph(
        char,
        ord(char),
        f"uni{ord(char):04X}",
        600,
        (CenterlineStroke(0, (Point(0, 0), Point(100, 100)), False),),
    )


def test_partial_cache_compiles_only_misses_and_force_rebuilds_requested(
    tmp_path: Path, test_font: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    compiled_chars: list[str] = []

    def record(*args):
        compiled_chars.append(args[1])
        return _fake_glyph(*args)

    monkeypatch.setattr(compiler, "_compile_glyph", record)
    first, _ = compile_centerline_font(test_font, {"A", "B"}, config)
    second, _ = compile_centerline_font(test_font, {"A", "B", "C"}, config)
    forced, _ = compile_centerline_font(test_font, {"A"}, config, force=True)

    assert compiled_chars == ["A", "B", "C", "A"]
    assert (first.cache_hits, first.cache_misses) == (0, 2)
    assert (second.cache_hits, second.cache_misses) == (2, 1)
    assert (forced.cache_hits, forced.cache_misses) == (0, 1)
    assert set(forced.glyphs) == {"A", "B", "C"}


def test_per_glyph_shard_survives_without_canonical_cache(
    tmp_path: Path, test_font: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(compiler, "_compile_glyph", _fake_glyph)
    first, target = compile_centerline_font(test_font, {"A"}, config)
    target.unlink()

    def unexpected_compile(*_args):
        raise AssertionError("valid shard must be loaded instead of recompiled")

    monkeypatch.setattr(compiler, "_compile_glyph", unexpected_compile)
    second, _ = compile_centerline_font(test_font, {"A"}, config)

    assert first.glyphs["A"] == second.glyphs["A"]
    assert (second.cache_hits, second.cache_misses) == (1, 0)
    assert glyph_shard_path(target, "A").is_file()
    assert shard_manifest_path(target).is_file()


def test_centerline_worker_policy_is_ram_capped_and_bounded() -> None:
    assert resolve_centerline_worker_count("auto", 20) <= 4
    assert resolve_centerline_worker_count(8, 3) == 3
    assert resolve_centerline_worker_count(8, 0) == 1
    with pytest.raises(ValueError, match="positive integer"):
        resolve_centerline_worker_count(0, 3)


def test_glyph_batch_publishes_manifest_once(
    tmp_path: Path, test_font: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(compiler, "_compile_glyph", _fake_glyph)
    original = compiler.write_shard_manifest_atomic
    writes: list[set[str]] = []

    def record_manifest(cache_path, *, identity, glyphs):
        writes.append(set(glyphs))
        return original(cache_path, identity=identity, glyphs=glyphs)

    monkeypatch.setattr(compiler, "write_shard_manifest_atomic", record_manifest)

    compiled, _ = compile_centerline_font(
        test_font, {"A", "B", "C"}, config, workers=1
    )

    assert set(compiled.glyphs) == {"A", "B", "C"}
    assert writes == [{"A", "B", "C"}]


def test_parallel_glyph_merge_matches_sequential_geometry(
    tmp_path: Path, test_font: Path
) -> None:
    config = replace(
        _config(tmp_path),
        em_resolution_px=128,
        padding_px=8,
        candidate_methods=("skeletonize",),
    )
    sequential, _ = compile_centerline_font(
        test_font,
        {"A", "B", "C"},
        config,
        cache_path=tmp_path / "sequential" / "centerlines.json",
        force=True,
        workers=1,
    )
    parallel, _ = compile_centerline_font(
        test_font,
        {"A", "B", "C"},
        config,
        cache_path=tmp_path / "parallel" / "centerlines.json",
        force=True,
        workers=2,
    )

    assert list(parallel.glyphs) == ["A", "B", "C"]
    assert parallel.glyphs == sequential.glyphs
    assert parallel.warnings == sequential.warnings


def test_rebuild_one_font_does_not_remove_another(
    tmp_path: Path, test_font: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(compiler, "_compile_glyph", _fake_glyph)
    _, path_a = compile_centerline_font(test_font, {"A"}, config)
    _, path_b = compile_centerline_font(Path("assets/1.ttf"), {"A"}, config)
    before_b = path_b.read_bytes()

    compile_centerline_font(test_font, {"A"}, config, force=True)

    assert path_a.is_file()
    assert path_b.read_bytes() == before_b


def test_corrupted_cache_is_safely_rebuilt(
    tmp_path: Path, test_font: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    target = default_cache_path(font_sha256(test_font), config)
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(compiler, "_compile_glyph", _fake_glyph)

    compiled, path = compile_centerline_font(test_font, {"A"}, config)

    assert set(compiled.glyphs) == {"A"}
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == "plotter-centerline-font"
    assert json.loads(metadata_path(path).read_text(encoding="utf-8"))["glyph_count"] == 1


def test_atomic_failure_leaves_no_partial_target(
    tmp_path: Path, test_font: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(compiler, "_compile_glyph", _fake_glyph)
    compiled, _ = compile_centerline_font(test_font, {"A"}, config)
    target = tmp_path / "atomic" / "centerlines.json"

    def fail_replace(_source, _target):
        raise OSError("interrupted")

    monkeypatch.setattr("plotter_processor.centerline_font.serializer.os.replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        write_centerline_font_atomic(compiled, target, config={})

    assert not target.exists()
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_make_font_cache_rebuild_creates_usable_cache(tmp_path: Path, test_font: Path) -> None:
    raw = load_yaml(Path("configs/layout.yaml"))
    raw["centerline"]["render"]["em_resolution_px"] = 512
    raw["centerline"]["render"]["padding_px"] = 16
    raw["centerline"]["skeleton"]["candidate_methods"] = ["skeletonize"]
    layout = tmp_path / "layout.yaml"
    layout.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("A", encoding="utf-8")
    cache_dir = tmp_path / "cache" / "font-cache"

    subprocess.run(
        [
            "make",
            "font-cache-rebuild",
            f"FONT={test_font}",
            f"FONT_CACHE_CORPUS={corpus}",
            f"FONT_CACHE_DIR={cache_dir}",
            f"CACHE_DIR={tmp_path / 'cache'}",
            f"LAYOUT_CONFIG={layout}",
            f"BUILD={tmp_path / 'build'}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    config = replace(load_centerline_config(raw), cache_directory=cache_dir)
    status = cache_status(test_font, config)

    assert status["valid"] is True
    assert status["cached_glyph_count"] == 1
    assert Path(str(status["cache_path"])).is_file()
