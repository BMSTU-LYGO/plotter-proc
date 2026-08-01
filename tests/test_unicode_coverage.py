import pytest

from plotter_processor.unicode_coverage import inspect_coverage


def test_coverage_reports_codepoint_name_and_missing_stably() -> None:
    result = inspect_coverage({ord("×"): "multiply"}, "basic_math")
    assert result["supported"] == 1
    assert result["symbols"][1]["codepoint"] == "U+00D7"
    assert any(item["char"] == "√" for item in result["missing"])


def test_unknown_coverage_group_is_error() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        inspect_coverage({}, "nope")
