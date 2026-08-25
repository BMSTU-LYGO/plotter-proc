from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from plotter_processor.omml_parser import parse_omml


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
    assert parsed.model is not None
    assert parsed.model.source_syntax == "omml"
    assert {node.kind for node in parsed.model.root.children} >= {
        "fraction", "superscript", "root"
    }


def test_unknown_node_is_reported_without_losing_text() -> None:
    element = parse_xml(
        f"<m:oMath {nsdecls('m')}><m:unknown><m:r><m:t>x</m:t></m:r>"
        "</m:unknown></m:oMath>"
    )

    parsed = parse_omml(element)

    assert parsed.expression == "x"
    assert parsed.warnings == ("omml_unsupported_node:unknown",)
