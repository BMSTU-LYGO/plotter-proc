from plotter_processor.pdf_math_detector import (
    PDFMathSpan,
    detect_pdf_math_regions,
)


def test_math_expression_is_detected_and_plain_sentence_is_not() -> None:
    spans = [
        PDFMathSpan("math", 0, 0, "x^2 + y^2 = z^2", (50, 50, 180, 70), "Helvetica", 16, 0),
        PDFMathSpan("text", 1, 0, "This is an ordinary sentence", (50, 90, 220, 105), "Helvetica", 11, 0),
    ]

    regions, warnings = detect_pdf_math_regions(
        spans, [], mode="auto", confidence_threshold=0.75,
        max_region_area_ratio=0.35, page_area=400 * 600,
    )

    assert len(regions) == 1
    assert regions[0].span_ids == ("math",)
    assert any("low_confidence" in warning for warning in warnings) is False


def test_nearby_fraction_line_boosts_visual_candidate() -> None:
    spans = [PDFMathSpan("fraction", 0, 0, "a+b", (100, 80, 135, 95), "Helvetica", 13, 0)]

    regions, _ = detect_pdf_math_regions(
        spans, [(98, 98, 140, 99)], mode="visual", confidence_threshold=0.75,
        max_region_area_ratio=0.35, page_area=400 * 600,
    )

    assert regions
    assert regions[0].drawing_indices == (0,)


def test_split_baseline_math_is_grouped_without_absorbing_plain_prose() -> None:
    spans = [
        PDFMathSpan("x", 0, 0, "x", (50, 50, 58, 66), "Times", 16, 0, 65),
        PDFMathSpan("sup", 0, 0, "2", (58, 44, 63, 54), "Times", 10, 1, 53),
        PDFMathSpan("eq", 0, 0, "+ y = 4", (65, 50, 112, 66), "Symbol", 16, 0, 65),
        PDFMathSpan(
            "prose", 1, 0, "This ordinary sentence has number 4",
            (50, 90, 250, 105), "Times", 11, 0, 104,
        ),
    ]

    regions, _ = detect_pdf_math_regions(
        spans,
        [],
        mode="auto",
        confidence_threshold=0.75,
        max_region_area_ratio=0.35,
        page_area=400 * 600,
    )

    assert len(regions) == 1
    assert set(regions[0].span_ids) == {"x", "sup", "eq"}
    assert "prose" not in regions[0].span_ids


def test_low_confidence_region_is_warning_not_false_positive() -> None:
    spans = [
        PDFMathSpan("maybe", 0, 0, "value + item", (20, 20, 90, 32), "Times", 11, 0)
    ]

    regions, warnings = detect_pdf_math_regions(
        spans,
        [],
        mode="auto",
        confidence_threshold=0.75,
        max_region_area_ratio=0.35,
        page_area=400 * 600,
    )

    assert not regions
    assert all("low_confidence" in warning for warning in warnings)
