from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_objects


@dataclass(frozen=True, slots=True)
class PreprocessedImage:
    grayscale: np.ndarray
    binary: np.ndarray
    original_size: tuple[int, int]
    working_size: tuple[int, int]
    warnings: tuple[str, ...]


def preprocess_image(
    image_path: str | Path,
    options: Mapping[str, object],
    *,
    debug_path: str | Path | None = None,
) -> PreprocessedImage:
    path = Path(image_path)
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            original_size = image.size
            max_pixels = _positive_int(options, "max_input_pixels")
            if original_size[0] * original_size[1] > max_pixels:
                raise ValueError(
                    f"Image exceeds images.max_input_pixels ({max_pixels}): {path}"
                )
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                image = Image.alpha_composite(background, rgba).convert("RGB")
            else:
                image = image.convert("RGB")
            max_side = _positive_int(options, "max_working_side_px")
            if max(image.size) > max_side:
                scale = max_side / max(image.size)
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            gray = ImageOps.grayscale(image)
            if bool(options.get("autocontrast", True)):
                gray = ImageOps.autocontrast(gray)
            sigma = float(options.get("blur_sigma", 0.6))
            if sigma > 0:
                gray = gray.filter(ImageFilter.GaussianBlur(sigma))
            grayscale = np.asarray(gray, dtype=np.float32) / 255.0
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"Cannot preprocess image: {path}") from error

    threshold_options = options.get("threshold", {})
    if not isinstance(threshold_options, Mapping):
        raise TypeError("images.threshold must be a mapping")
    method = str(threshold_options.get("method", "otsu"))
    if method == "otsu":
        threshold = float(threshold_otsu(grayscale)) if np.ptp(grayscale) > 0 else 0.5
    elif method == "fixed":
        threshold = float(threshold_options.get("value", 160)) / 255.0
    else:
        raise ValueError(f"Unknown image threshold method: {method}")
    binary = grayscale < threshold
    minimum = int(options.get("remove_small_objects_px", 12))
    if minimum > 0:
        binary = remove_small_objects(binary, max_size=minimum - 1)
    warnings: list[str] = []
    if not binary.any():
        warnings.append("blank_image")
    if debug_path is not None:
        debug = Path(debug_path)
        debug.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray((~binary * 255).astype(np.uint8), mode="L").save(debug)
    return PreprocessedImage(
        grayscale, binary, original_size, (grayscale.shape[1], grayscale.shape[0]), tuple(warnings)
    )


def _positive_int(options: Mapping[str, object], key: str) -> int:
    value = options.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Missing or invalid positive field: images.{key}")
    return value
