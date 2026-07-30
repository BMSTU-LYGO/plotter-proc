from __future__ import annotations

import hashlib
import json
from pathlib import Path

from plotter_processor.centerline_font.config import CenterlineConfig


def font_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(font_hash: str, config: CenterlineConfig) -> str:
    payload = json.dumps(config.serializable(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{font_hash}\0{payload}".encode()).hexdigest()


def default_cache_path(font_hash: str, config: CenterlineConfig) -> Path:
    return config.cache_directory / cache_key(font_hash, config) / "centerlines.json"
