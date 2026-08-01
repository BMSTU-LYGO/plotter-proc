import json
from pathlib import Path

from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from plotter_processor.omml_parser import parse_omml
from plotter_processor.pipeline import PipelineOptions, run_pipeline


def test_fraction_radical_and_scripts() -> None:
    element = parse_xml(
        f"<m:oMathPara {nsdecls('m')}><m:oMath>"
        "<m:f><m:num><m:r><m:t>a</m:t></m:r></m:num>"
        "<m:den><m:r><m:t>b</m:t></m:r></m:den></m:f>"
        "<m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e>"
        "<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>"
        "<m:rad><m:e><m:r><m:t>y</m:t></m:r></m:e></m:rad>"
        "</m:oMath></m:oMathPara>"
    )

    parsed = parse_omml(element)

    assert parsed.display_mode is True
    assert parsed.expression == r"\frac{a}{b}{x}^{2}\sqrt{y}"
    assert not parsed.warnings


def test_unknown_node_is_reported_without_losing_text() -> None:
    element = parse_xml(
        f"<m:oMath {nsdecls('m')}><m:unknown><m:r><m:t>x</m:t></m:r>"
        "</m:unknown></m:oMath>"
    )

    parsed = parse_omml(element)

    assert parsed.expression == "x"
    assert parsed.warnings == ("omml_unsupported_node:unknown",)


def test_basic_omml_reaches_centerline_pipeline(tmp_path: Path, test_font: Path) -> None:
    output = tmp_path / "omml"
    result = run_pipeline(PipelineOptions(
        Path("tests/fixtures/update_7/latex/omml_basic.docx"),
        test_font,
        "A5",
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        output,
        font_mode="outline",
        latex_debug=True,
    ))

    assert result.status == "ok", result.error
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["latex"]["omml_expressions"] == 1
    assert "omml_equation_not_supported" not in report["warnings"]
