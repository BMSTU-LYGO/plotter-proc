from __future__ import annotations

import hashlib
import json
import os
import pickle
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from plotter_processor.schemas import STAGE_CACHE_SCHEMA_VERSION

ValueT = TypeVar("ValueT")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_fingerprint(
    stage: str,
    *,
    input_fingerprint: str,
    algorithm_version: str,
    settings: Mapping[str, object] | None = None,
) -> str:
    """Hash only the declared inputs of one stage."""
    payload = {
        "stage": stage,
        "input": input_fingerprint,
        "algorithm_version": algorithm_version,
        "settings": _json_value(settings or {}),
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheLookup(Generic[ValueT]):
    hit: bool
    value: ValueT | None = None


@dataclass(slots=True)
class StageCacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    corrupt_entries: int = 0


class StageCacheManager:
    """Shared disposable cache with versioned, atomic stage entries."""

    def __init__(
        self,
        root: Path,
        *,
        schema_version: int = STAGE_CACHE_SCHEMA_VERSION,
    ) -> None:
        self.root = root
        self.schema_version = schema_version
        self.stats: dict[str, StageCacheStats] = {}

    def load(self, stage: str, fingerprint: str) -> CacheLookup[object]:
        stats = self.stats.setdefault(stage, StageCacheStats())
        path = self.entry_path(stage, fingerprint)
        if not path.is_file():
            stats.misses += 1
            return CacheLookup(False)
        try:
            with path.open("rb") as stream:
                envelope = pickle.load(stream)
            if not isinstance(envelope, dict):
                raise TypeError("cache envelope is not a mapping")
            if envelope.get("schema_version") != self.schema_version:
                raise ValueError("unsupported cache schema")
            if envelope.get("stage") != stage:
                raise ValueError("stage mismatch")
            if envelope.get("fingerprint") != fingerprint:
                raise ValueError("fingerprint mismatch")
        except (EOFError, OSError, pickle.PickleError, TypeError, ValueError):
            stats.misses += 1
            stats.corrupt_entries += 1
            return CacheLookup(False)
        stats.hits += 1
        return CacheLookup(True, envelope.get("payload"))

    def store(self, stage: str, fingerprint: str, value: object) -> Path:
        path = self.entry_path(stage, fingerprint)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": self.schema_version,
            "stage": stage,
            "fingerprint": fingerprint,
            "payload": value,
        }
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as stream:
                temporary = Path(stream.name)
                pickle.dump(envelope, stream, protocol=pickle.HIGHEST_PROTOCOL)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.stats.setdefault(stage, StageCacheStats()).writes += 1
        return path

    def entry_path(self, stage: str, fingerprint: str) -> Path:
        return self.root / stage / fingerprint / "entry.pickle"

    def assets_directory(self, stage: str, fingerprint: str) -> Path:
        path = self.entry_path(stage, fingerprint).parent / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def report(self) -> dict[str, dict[str, int]]:
        return {
            stage: {
                "hits": stats.hits,
                "misses": stats.misses,
                "writes": stats.writes,
                "corrupt_entries": stats.corrupt_entries,
            }
            for stage, stats in sorted(self.stats.items())
        }


def _json_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported stage fingerprint value: {type(value).__name__}")
