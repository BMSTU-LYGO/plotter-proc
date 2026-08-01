import numpy as np

from plotter_processor.centerline_font.counter_analysis import analyze_counters


def _ring() -> np.ndarray:
    mask = np.zeros((21, 21), dtype=bool)
    mask[3:18, 3:18] = True
    mask[7:14, 7:14] = False
    return mask


def test_counter_is_detected_and_preserved() -> None:
    mask = _ring()
    reconstructed = mask.copy()
    result = analyze_counters(mask, reconstructed)
    assert result.significant_count == 1
    assert result.preservation_ratio == 1.0


def test_filled_counter_is_reported_as_lost() -> None:
    mask = _ring()
    reconstructed = np.ones_like(mask)
    result = analyze_counters(mask, reconstructed)
    assert result.significant_count == 1
    assert result.preservation_ratio == 0.0
