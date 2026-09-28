"""Cheap runtime access to a precompiled centerline font cache.

This module deliberately has no compiler fallback: normal document processing
may only consume an artifact produced by the offline font compiler.
"""

from __future__ import annotations

from pathlib import Path

from plotter_processor.centerline_font.models import CenterlineGlyph, CompiledCenterlineFont
from plotter_processor.centerline_font.serializer import load_centerline_font


class FastFont:
    """An immutable-in-practice, cache-only glyph lookup table."""

    _loaded: dict[Path, "FastFont"] = {}

    def __init__(self, compiled: CompiledCenterlineFont, fallback: CenterlineGlyph | None) -> None:
        self.compiled = compiled
        self._fallback = fallback

    @classmethod
    def load(cls, path: str | Path, *, fallback_char: str | None = "?") -> "FastFont":
        """Load a serialized centerline cache once per resolved path.

        ``path`` is a cache file, not a TTF.  Missing glyphs return the chosen
        cached fallback (or ``None``); they never trigger compilation.
        """
        source = Path(path).resolve()
        cached = cls._loaded.get(source)
        if cached is not None:
            return cached
        compiled, _ = load_centerline_font(source)
        fallback = compiled.glyphs.get(fallback_char) if fallback_char else None
        loaded = cls(compiled, fallback)
        cls._loaded[source] = loaded
        return loaded

    @classmethod
    def clear_cache(cls) -> None:
        """Forget process-local cache entries (primarily useful in tests)."""
        cls._loaded.clear()

    def get(self, char: str) -> CenterlineGlyph | None:
        """Return a glyph in O(1), with an explicit precompiled fallback."""
        return self.compiled.glyphs.get(char, self._fallback)

    @property
    def units_per_em(self) -> int:
        return self.compiled.units_per_em

    @property
    def font_id(self) -> str:
        return self.compiled.font_sha256

    def __contains__(self, char: str) -> bool:
        return char in self.compiled.glyphs
