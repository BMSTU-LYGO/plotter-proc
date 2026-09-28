from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from plotter_processor.centerline_font.cache import font_sha256
from plotter_processor.font_loader import LoadedFont, load_font
from plotter_processor.models import FontIdentity


@dataclass(frozen=True, slots=True)
class FontSource:
    path: Path
    role: str
    sha256: str


class FontRegistry:
    """An opened primary font plus ordered fallbacks for legacy character layout."""

    def __init__(self, primary: LoadedFont, fallbacks: list[tuple[str, LoadedFont]]) -> None:
        self.primary = primary
        self.fallbacks = fallbacks
        # These keep existing layout code's primary vertical metrics stable.
        self.path = primary.path
        self.font = primary.font
        self.glyph_set = primary.glyph_set
        self.metrics = primary.metrics
        self.advances = primary.advances
        self.warnings = primary.warnings
        self.cmap = {**primary.cmap}
        for _, font in fallbacks:
            for codepoint, glyph_name in font.cmap.items():
                self.cmap.setdefault(codepoint, glyph_name)

    @property
    def sources(self) -> list[tuple[str, LoadedFont]]:
        return [("primary", self.primary), *self.fallbacks]

    def font_for_char(self, char: str) -> tuple[str, LoadedFont]:
        if char.isspace():
            return "primary", self.primary
        for role, font in self.sources:
            if ord(char) in font.cmap:
                return role, font
        checked = ", ".join(str(font.path) for _, font in self.sources)
        raise ValueError(
            f"No font in fallback chain supports U+{ord(char):04X}; checked: {checked}"
        )

    def identity_for_char(self, char: str) -> FontIdentity:
        _, font = self.font_for_char(char)
        return FontIdentity(font.path.stem, font.path, font_sha256(font.path))

    def role_for_char(self, char: str) -> str:
        return self.font_for_char(char)[0]

    def font_for_sha256(self, digest: str | None) -> LoadedFont:
        for _, font in self.sources:
            if digest is None or font_sha256(font.path) == digest:
                return font
        raise ValueError(f"Unknown font digest in positioned glyph: {digest}")

    def glyph_name_for_char(self, char: str) -> str:
        return self.font_for_char(char)[1].glyph_name_for_char(char)

    def advance_for_char(self, char: str) -> int:
        _, font = self.font_for_char(char)
        return font.advance_for_glyph(font.glyph_name_for_char(char))

    def scale_for_char(self, char: str, primary_scale: float) -> float:
        _, font = self.font_for_char(char)
        return primary_scale * self.primary.metrics.units_per_em / font.metrics.units_per_em

    def advance_for_glyph(self, glyph_name: str) -> int:
        # Compatibility for code that only has a glyph name. New layout paths use
        # advance_for_char so duplicate glyph names across fonts remain unambiguous.
        for _, font in self.sources:
            if glyph_name in font.advances:
                return font.advance_for_glyph(glyph_name)
        return self.primary.advance_for_glyph(glyph_name)

    def validate_text(self, text: str) -> None:
        for char in text:
            if char.isprintable() and not char.isspace():
                self.font_for_char(char)

    def close(self) -> None:
        self.primary.close()
        for _, font in self.fallbacks:
            font.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def load_font_registry(primary: Path, fallbacks: list[tuple[str, Path]]) -> FontRegistry:
    opened: list[LoadedFont] = []
    try:
        main = load_font(primary)
        opened.append(main)
        fallback_fonts: list[tuple[str, LoadedFont]] = []
        for role, path in fallbacks:
            item = load_font(path)
            opened.append(item)
            fallback_fonts.append((role, item))
        return FontRegistry(main, fallback_fonts)
    except Exception:
        for font in opened:
            font.close()
        raise


def select_font_for_cluster(
    cluster: str, primary: Path, fallbacks: list[tuple[str, Path]]
) -> FontSource:
    checked: list[Path] = []
    for role, path in [("primary", primary), *fallbacks]:
        checked.append(path)
        with load_font(path) as font:
            if all(ord(char) in font.cmap for char in cluster if not char.isspace()):
                return FontSource(path, role, font_sha256(path))
    details = ", ".join(str(path) for path in checked)
    chars = " ".join(f"U+{ord(char):04X}" for char in cluster)
    raise ValueError(f"No font in fallback chain supports cluster {chars}; checked: {details}")
