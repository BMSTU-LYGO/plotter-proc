from dataclasses import replace
from pathlib import Path

import pytest

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml

REVIEW_GLYPHS = ";.…:?ЩЦШUИЙЮ"


def test_centerline_corpus_contains_required_regression_glyphs() -> None:
    text = Path("examples/centerline_glyph_corpus.txt").read_text(encoding="utf-8")
    required = set(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789.,!?;:-()«»"
    )
    assert required <= set(text)
    assert len([char for char in text if not char.isspace()]) == len(required)


@pytest.fixture(scope="module")
def review_glyphs(tmp_path_factory: pytest.TempPathFactory):
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    config = replace(config, em_resolution_px=256, padding_px=16, font_overrides={})
    compiled, _ = compile_centerline_font(
        Path("assets/1.ttf"),
        set(REVIEW_GLYPHS),
        config,
        cache_path=tmp_path_factory.mktemp("review-glyphs") / "font.json",
        force=True,
    )
    return compiled.glyphs


def test_review_glyph_corpus_has_truthful_quality_and_topology(review_glyphs) -> None:
    expected_components = {".": 1, ":": 2, ";": 2, "…": 3, "?": 2}
    for char in REVIEW_GLYPHS:
        quality = review_glyphs[char].quality
        assert quality["mask_coverage"] >= 0.94
        assert quality["centerline_inside_mask_ratio"] >= 0.999
        assert not quality["needs_review"]
        assert quality["quality_status"] == "auto_passed"
        assert quality["excess_retrace_length"] == 0
        if char in expected_components:
            assert quality["centerline_components"] == expected_components[char]
            assert quality["strokes_after_routing"] == expected_components[char]
            assert quality["retrace_ratio"] == 0


def test_review_capitals_do_not_exceed_theoretical_retrace(review_glyphs) -> None:
    maximum_retrace = {
        "U": 0.20,
        "И": 0.20,
        "Й": 0.18,
        "Ц": 0.18,
        "Ш": 0.28,
        "Щ": 0.25,
        "Ю": 0.18,
    }
    for char, maximum in maximum_retrace.items():
        quality = review_glyphs[char].quality
        assert quality["strokes_after_routing"] == quality["centerline_components"]
        assert quality["minimum_one_route_retrace_length"] > 0
        assert quality["retrace_ratio"] <= maximum
        assert quality["excess_retrace_length"] == 0
