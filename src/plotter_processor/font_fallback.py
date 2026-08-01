from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from plotter_processor.centerline_font.cache import font_sha256
from plotter_processor.font_loader import load_font


@dataclass(frozen=True, slots=True)
class FontSource:
    path: Path
    role: str
    sha256: str


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
