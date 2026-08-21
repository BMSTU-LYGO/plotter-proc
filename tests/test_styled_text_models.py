from plotter_processor.document_models import SourceParagraph, SourceTextRun, SourceTextStyle


def test_styled_paragraph_keeps_text_and_underline() -> None:
    paragraph = SourceParagraph((SourceTextRun("under", SourceTextStyle(underline="double")), SourceTextRun(" normal")))
    assert paragraph.text == "under normal"
    assert paragraph.runs[0].style.underline == "double"
