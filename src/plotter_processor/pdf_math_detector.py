from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PDFMathSpan:
    id: str
    block_index: int
    line_index: int
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    flags: int


@dataclass(frozen=True, slots=True)
class PDFMathRegion:
    id: str
    bbox: tuple[float, float, float, float]
    confidence: float
    span_ids: tuple[str, ...]
    block_indices: tuple[int, ...]
    drawing_indices: tuple[int, ...]
    text: str


def collect_pdf_spans(blocks: list[dict[str, object]]) -> list[PDFMathSpan]:
    result: list[PDFMathSpan] = []
    for block_index, block in enumerate(blocks):
        if block.get("type") != 0:
            continue
        for line_index, line in enumerate(block.get("lines", [])):
            for span_index, span in enumerate(line.get("spans", [])):
                text = str(span.get("text", ""))
                bbox = _bbox(span.get("bbox"))
                if not text.strip() or bbox is None:
                    continue
                result.append(PDFMathSpan(
                    f"b{block_index}-l{line_index}-s{span_index}",
                    block_index,
                    line_index,
                    text,
                    bbox,
                    str(span.get("font", "")),
                    float(span.get("size", 0.0)),
                    int(span.get("flags", 0)),
                ))
    return result


def detect_pdf_math_regions(
    spans: list[PDFMathSpan],
    drawing_rects: list[tuple[float, float, float, float]],
    *,
    mode: str = "auto",
    confidence_threshold: float = 0.75,
    max_region_area_ratio: float = 0.35,
    page_area: float,
) -> tuple[list[PDFMathRegion], list[str]]:
    if mode not in {"auto", "visual", "off"}:
        raise ValueError(f"Unknown PDF math mode: {mode}")
    if mode == "off":
        return [], []
    threshold = confidence_threshold if mode == "auto" else min(confidence_threshold, 0.55)
    candidates: list[tuple[PDFMathSpan, float, tuple[int, ...]]] = []
    warnings: list[str] = []
    for span in spans:
        nearby = tuple(
            index
            for index, rect in enumerate(drawing_rects)
            if _near_horizontal_line(rect, span.bbox)
        )
        confidence = _span_confidence(span, bool(nearby))
        if confidence >= threshold:
            candidates.append((span, confidence, nearby))
        elif confidence >= 0.45:
            warnings.append(f"pdf_math_candidate_low_confidence:{span.id}:{confidence:.2f}")
    regions: list[PDFMathRegion] = []
    for span, confidence, drawings in candidates:
        if any(span.id in region.span_ids for region in regions):
            continue
        grouped = [item for item in candidates if _can_group(span.bbox, item[0].bbox)]
        grouped_spans = [item[0] for item in grouped]
        bbox = _union([item.bbox for item in grouped_spans])
        area_ratio = _area(bbox) / max(page_area, 1.0)
        if area_ratio > max_region_area_ratio:
            warnings.append(f"pdf_math_region_too_large:{span.id}:{area_ratio:.3f}")
            continue
        drawing_ids = sorted({index for item in grouped for index in item[2]})
        regions.append(PDFMathRegion(
            f"pdf-formula-{len(regions) + 1:03d}",
            bbox,
            round(max(item[1] for item in grouped), 4),
            tuple(item.id for item in grouped_spans),
            tuple(sorted({item.block_index for item in grouped_spans})),
            tuple(drawing_ids),
            " ".join(item.text for item in grouped_spans),
        ))
    return regions, list(dict.fromkeys(warnings))


def _span_confidence(span: PDFMathSpan, nearby_line: bool) -> float:
    text = span.text.strip()
    if not text:
        return 0.0
    math_symbols = set("=+−-×÷∑∫√≤≥≠∞αβγπ^_{}")
    symbol_count = sum(character in math_symbols for character in text)
    letters = sum(character.isalpha() for character in text)
    words = [word for word in text.replace("=", " ").split() if word.isalpha()]
    score = 0.0
    score += 0.32 if "=" in text else 0.0
    score += min(0.28, symbol_count / max(len(text), 1) * 1.4)
    score += 0.18 if any(character in "^_∑∫√" for character in text) else 0.0
    score += 0.18 if nearby_line else 0.0
    score += 0.25 if any(name in span.font.lower() for name in ("math", "symbol", "stix", "cm")) else 0.0
    score += 0.12 if any(character.isdigit() for character in text) else 0.0
    score += 0.10 if letters and len(words) <= 2 else 0.0
    if len(words) >= 4:
        score -= 0.35
    return max(0.0, min(1.0, score))


def _near_horizontal_line(
    rect: tuple[float, float, float, float], span: tuple[float, float, float, float]
) -> bool:
    width, height = rect[2] - rect[0], rect[3] - rect[1]
    horizontal = width >= 8 and height <= 3
    x_overlap = max(0.0, min(rect[2], span[2] + 20) - max(rect[0], span[0] - 20))
    y_distance = min(abs(rect[1] - span[3]), abs(span[1] - rect[3]))
    return horizontal and x_overlap > 0 and y_distance <= 24


def _can_group(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> bool:
    x_gap = max(0.0, max(left[0], right[0]) - min(left[2], right[2]))
    y_gap = max(0.0, max(left[1], right[1]) - min(left[3], right[3]))
    return x_gap <= 40 and y_gap <= 24


def _union(rectangles: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(rect[0] for rect in rectangles),
        min(rect[1] for rect in rectangles),
        max(rect[2] for rect in rectangles),
        max(rect[3] for rect in rectangles),
    )


def _area(rect: tuple[float, float, float, float]) -> float:
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return tuple(float(item) for item in value)  # type: ignore[return-value]
