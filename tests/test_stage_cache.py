from pathlib import Path

from plotter_processor.performance import StageTimings
from plotter_processor.pipeline_stages import NORMALIZE_LAYOUT, READ_DOCUMENT, StageExecutor
from plotter_processor.stage_cache import StageCacheManager, stage_fingerprint


def test_stage_fingerprint_uses_only_declared_settings() -> None:
    base = stage_fingerprint(
        "layout",
        input_fingerprint="document",
        algorithm_version="1",
        settings={"page": "A5", "margin": 10},
    )
    reordered = stage_fingerprint(
        "layout",
        input_fingerprint="document",
        algorithm_version="1",
        settings={"margin": 10, "page": "A5"},
    )
    changed = stage_fingerprint(
        "layout",
        input_fingerprint="document",
        algorithm_version="1",
        settings={"page": "A4", "margin": 10},
    )

    assert base == reordered
    assert base != changed


def test_two_stages_share_cache_rules_and_corruption_is_local(tmp_path: Path) -> None:
    cache = StageCacheManager(tmp_path / "cache")
    first = StageExecutor(StageTimings())
    calls = {"read": 0, "layout": 0}

    def read(value: str) -> dict[str, str]:
        calls["read"] += 1
        return {"document": value}

    def layout(value: dict[str, str]) -> tuple[str, ...]:
        calls["layout"] += 1
        return (value["document"],)

    document = first.run_cached(
        READ_DOCUMENT,
        "input.docx",
        read,
        cache=cache,
        fingerprint="document-fingerprint",
    )
    result = first.run_cached(
        NORMALIZE_LAYOUT,
        document,
        layout,
        cache=cache,
        fingerprint="layout-fingerprint",
    )
    second = StageExecutor(StageTimings())
    assert second.run_cached(
        READ_DOCUMENT,
        "input.docx",
        read,
        cache=cache,
        fingerprint="document-fingerprint",
    ) == document
    assert second.run_cached(
        NORMALIZE_LAYOUT,
        document,
        layout,
        cache=cache,
        fingerprint="layout-fingerprint",
    ) == result
    assert calls == {"read": 1, "layout": 1}

    cache.entry_path("layout", "layout-fingerprint").write_bytes(b"broken")
    rebuilt = StageExecutor(StageTimings()).run_cached(
        NORMALIZE_LAYOUT,
        document,
        layout,
        cache=cache,
        fingerprint="layout-fingerprint",
    )
    assert rebuilt == result
    assert calls == {"read": 1, "layout": 2}
    assert cache.stats["layout"].corrupt_entries == 1


def test_unsupported_stage_cache_schema_is_ignored(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    StageCacheManager(root, schema_version=1).store("layout", "fingerprint", "old")

    lookup = StageCacheManager(root).load("layout", "fingerprint")

    assert not lookup.hit
