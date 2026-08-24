from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from plotter_processor.centerline_font.config import CenterlineConfig

SHARD_CACHE_VERSION = 9


def font_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def centerline_config_fingerprint(
    config: CenterlineConfig, *, font_hash: str | None = None
) -> str:
    """Hash only settings that can change a compiled centerline artifact."""
    payload = centerline_config_payload(config, font_hash=font_hash)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def centerline_config_payload(
    config: CenterlineConfig, *, font_hash: str | None = None
) -> dict[str, object]:
    payload = config.serializable()
    for key in (
        "cache_enabled",
        "cache_directory",
        "debug_enabled",
        "fail_on_low_quality",
    ):
        payload.pop(key, None)
    patch = config.glyph_patch_file
    payload["glyph_patch_sha256"] = (
        font_sha256(patch) if patch is not None and patch.is_file() else None
    )
    payload.pop("glyph_patch_file", None)
    if font_hash is not None:
        overrides = config.font_overrides.get(font_hash.lower(), {})
        payload["font_overrides"] = {font_hash.lower(): overrides} if overrides else {}
    return payload


def cache_key(font_hash: str, config: CenterlineConfig) -> str:
    """Compatibility helper for callers that need the complete stable identity."""
    return f"{font_hash}/{centerline_config_fingerprint(config, font_hash=font_hash)}"


def default_cache_path(font_hash: str, config: CenterlineConfig) -> Path:
    return config.cache_directory / cache_key(font_hash, config) / "centerlines.json"


def metadata_path(cache_path: Path) -> Path:
    return (
        cache_path.with_name("metadata.json")
        if cache_path.name == "centerlines.json"
        else cache_path.with_suffix(cache_path.suffix + ".metadata.json")
    )


def shard_manifest_path(cache_path: Path) -> Path:
    return cache_path.parent / "manifest.json"


def glyph_shard_path(cache_path: Path, char: str) -> Path:
    return cache_path.parent / "glyphs" / f"U+{ord(char):06X}.json"


def shard_identity(
    font_hash: str, config: CenterlineConfig
) -> dict[str, object]:
    return {
        "format": "plotter-centerline-font-shards",
        "version": SHARD_CACHE_VERSION,
        "font_sha256": font_hash,
        "algorithm_version": config.algorithm_version,
        "config_fingerprint": centerline_config_fingerprint(
            config, font_hash=font_hash
        ),
    }


def load_shard_manifest(
    cache_path: Path, *, identity: dict[str, object]
) -> dict[str, object] | None:
    target = shard_manifest_path(cache_path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in identity.items()
    ):
        return None
    glyphs = payload.get("glyphs")
    if not isinstance(glyphs, list) or any(not isinstance(item, str) for item in glyphs):
        return None
    return payload


def write_shard_manifest_atomic(
    cache_path: Path,
    *,
    identity: dict[str, object],
    glyphs: set[str] | list[str],
) -> Path:
    target = shard_manifest_path(cache_path)
    payload = {
        **identity,
        "glyphs": sorted(set(glyphs), key=ord),
    }
    _write_json_atomic(target, payload)
    return target


def _write_json_atomic(target: Path, payload: dict[str, object]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_cache_metadata_atomic(
    cache_path: Path,
    *,
    font_hash: str,
    font_path: Path,
    config: CenterlineConfig,
    glyph_count: int,
) -> Path:
    target = metadata_path(cache_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "font_sha256": font_hash,
        "font_path_hint": str(font_path),
        "algorithm_version": config.algorithm_version,
        "config_fingerprint": centerline_config_fingerprint(config, font_hash=font_hash),
        "created_at": datetime.now(UTC).isoformat(),
        "glyph_count": glyph_count,
    }
    _write_json_atomic(target, payload)
    return target


def cache_status(font_path: str | Path, config: CenterlineConfig) -> dict[str, object]:
    source = Path(font_path)
    digest = font_sha256(source)
    target = default_cache_path(digest, config)
    glyph_count = 0
    valid = False
    manifest = load_shard_manifest(target, identity=shard_identity(digest, config))
    if manifest is not None:
        glyph_count = len(manifest["glyphs"])
        valid = True
    elif target.is_file():
        try:
            from plotter_processor.centerline_font.serializer import load_centerline_font

            compiled, cached_config = load_centerline_font(target)
            glyph_count = len(compiled.glyphs)
            valid = (
                compiled.font_sha256 == digest
                and cached_config == centerline_config_payload(config, font_hash=digest)
            )
        except (TypeError, ValueError):
            valid = False
    namespace = target.parent
    size_bytes = sum(
        item.stat().st_size for item in namespace.rglob("*") if item.is_file()
    ) if namespace.is_dir() else 0
    return {
        "cache_directory": str(config.cache_directory),
        "cache_path": str(target),
        "font_sha256": digest,
        "algorithm_version": config.algorithm_version,
        "config_fingerprint": centerline_config_fingerprint(config, font_hash=digest),
        "cached_glyph_count": glyph_count,
        "cache_size_bytes": size_bytes,
        "exists": target.is_file() or manifest is not None,
        "valid": valid,
    }
