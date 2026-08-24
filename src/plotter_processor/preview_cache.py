from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PREVIEW_CACHE_VERSION = 1


@dataclass(frozen=True, slots=True)
class PreviewCacheResult:
    hit: bool
    cache_path: Path


def materialize_cached_preview(
    cache_directory: Path,
    kind: str,
    fingerprint_payload: dict[str, object],
    output_path: Path,
    render: Callable[[Path], None],
) -> PreviewCacheResult:
    """Copy an exact reusable preview or render and atomically publish it."""
    serialized = json.dumps(
        {
            "version": PREVIEW_CACHE_VERSION,
            "kind": kind,
            **fingerprint_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    target = cache_directory / kind / f"{fingerprint}.svg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        shutil.copyfile(target, output_path)
        return PreviewCacheResult(True, target)

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        render(temporary)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    shutil.copyfile(target, output_path)
    return PreviewCacheResult(False, target)
