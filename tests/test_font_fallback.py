from pathlib import Path

import pytest

from plotter_processor.font_fallback import select_font_for_cluster


def test_primary_is_preferred_when_it_has_symbol() -> None:
    result = select_font_for_cluster("π", Path("assets/1.ttf"), [])
    assert result.role == "primary"


def test_math_symbol_uses_fallback() -> None:
    result = select_font_for_cluster(
        "α",
        Path("assets/1.ttf"),
        [("math", Path("/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf"))],
    )
    assert result.role == "math"


def test_missing_symbol_lists_checked_fonts() -> None:
    with pytest.raises(ValueError, match="fallback chain"):
        select_font_for_cluster("͸", Path("assets/1.ttf"), [])
