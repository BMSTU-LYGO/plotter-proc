from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from fontTools.ttLib import TTFont, TTLibError

from plotter_processor.models import FontMetrics


@dataclass(slots=True, eq=False)
class LoadedFont:
    path: Path
    font: TTFont
    glyph_set: Any
    cmap: dict[int, str]
    metrics: FontMetrics
    advances: dict[str, int]
    warnings: list[str] = field(default_factory=list)

    def glyph_name_for_char(self, char: str) -> str:
        if len(char) != 1:
            raise ValueError("Expected exactly one character")
        try:
            return self.cmap[ord(char)]
        except KeyError as error:
            raise ValueError(
                f'Font is missing required glyph: "{char}" (U+{ord(char):04X})'
            ) from error

    def advance_for_glyph(self, glyph_name: str) -> int:
        metric = self.advances.get(glyph_name)
        if metric is not None:
            return metric
        fallback = round(self.metrics.units_per_em * 0.33)
        warning = f"Glyph {glyph_name!r} has no hmtx advance; using {fallback} font units"
        if warning not in self.warnings:
            self.warnings.append(warning)
        return fallback

    def validate_text(self, text: str) -> None:
        missing = sorted(
            {character for character in text if character.isprintable() and not character.isspace()}
            - {chr(codepoint) for codepoint in self.cmap}
        )
        if missing:
            details = ", ".join(f'"{char}" (U+{ord(char):04X})' for char in missing)
            raise ValueError(f"Font is missing {len(missing)} required glyphs: {details}")

    def close(self) -> None:
        self.font.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def load_font(path: str | Path) -> LoadedFont:
    font_path = Path(path)
    if not font_path.is_file():
        raise FileNotFoundError(f"Font file does not exist: {font_path}")
    try:
        font = TTFont(font_path, lazy=False)
    except (OSError, TTLibError) as error:
        raise ValueError(f"Cannot open TTF font: {font_path}") from error

    try:
        for table in ("head", "hhea", "hmtx", "cmap"):
            if table not in font:
                raise ValueError(f"Font is missing required table: {table}")
        units_per_em = int(font["head"].unitsPerEm)
        if units_per_em <= 0:
            raise ValueError("Font unitsPerEm must be positive")
        cmap = font.getBestCmap() or {}
        if not cmap:
            raise ValueError("Font contains no usable cmap")
        hhea = font["hhea"]
        advances = {
            name: int(metric[0]) for name, metric in font["hmtx"].metrics.items()
        }
        return LoadedFont(
            path=font_path,
            font=font,
            glyph_set=font.getGlyphSet(),
            cmap=dict(cmap),
            metrics=FontMetrics(
                units_per_em=units_per_em,
                ascent=int(hhea.ascent),
                descent=int(hhea.descent),
                line_gap=int(hhea.lineGap),
            ),
            advances=advances,
        )
    except Exception:
        font.close()
        raise
