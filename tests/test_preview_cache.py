from pathlib import Path

from plotter_processor.preview_cache import materialize_cached_preview


def test_preview_cache_renders_once_and_materializes_exact_hit(tmp_path: Path) -> None:
    calls: list[Path] = []

    def render(path: Path) -> None:
        calls.append(path)
        path.write_text("<svg>stable</svg>\n", encoding="utf-8")

    first_output = tmp_path / "first.svg"
    second_output = tmp_path / "second.svg"
    first = materialize_cached_preview(
        tmp_path / "cache", "font", {"font": "abc", "glyphs": ["A"]}, first_output, render
    )
    second = materialize_cached_preview(
        tmp_path / "cache", "font", {"font": "abc", "glyphs": ["A"]}, second_output, render
    )

    assert first.hit is False
    assert second.hit is True
    assert len(calls) == 1
    assert first_output.read_bytes() == second_output.read_bytes()


def test_preview_cache_fingerprint_change_is_a_miss(tmp_path: Path) -> None:
    def render(path: Path) -> None:
        path.write_text("<svg/>\n", encoding="utf-8")

    first = materialize_cached_preview(
        tmp_path / "cache", "font", {"glyphs": ["A"]}, tmp_path / "a.svg", render
    )
    second = materialize_cached_preview(
        tmp_path / "cache", "font", {"glyphs": ["B"]}, tmp_path / "b.svg", render
    )

    assert first.cache_path != second.cache_path
    assert second.hit is False
