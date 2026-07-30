import json
from pathlib import Path

import pymupdf
from docx import Document

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _create_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("Привет, это небольшой тест. 0123456789")
    document.save(path)


def _options(source: Path, output: Path, font: Path) -> PipelineOptions:
    return PipelineOptions(
        input_path=source,
        font_path=font,
        page="A5",
        size="normal",
        layout_config_path=Path("configs/layout.yaml"),
        machine_config_path=Path("configs/machine.yaml"),
        output_dir=output,
    )


def test_runs_complete_pipeline_and_writes_report(tmp_path: Path, test_font: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "build"
    _create_docx(source)

    result = run_pipeline(_options(source, output, test_font))

    assert result.status == "ok", result.error
    for filename in (
        "extracted.txt",
        "font-preview.svg",
        "plotter-preview.svg",
        "paths.json",
        "output.gcode",
        "report.json",
    ):
        assert (output / filename).is_file()
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["pipeline"] == "ttf-vector"
    assert report["statistics"]["characters"] > 0
    assert report["statistics"]["strokes"] > 0
    assert "G28" not in (output / "output.gcode").read_text(encoding="utf-8")
    assert not (output / "page.png").exists()
    assert not (output / "skeleton.png").exists()


def test_txt_and_pdf_end_to_end(tmp_path: Path, test_font: Path) -> None:
    txt = tmp_path / "input.txt"
    txt.write_text("Привет, мир!\nЁжик идёт домой.\n1234567890", encoding="utf-8")
    assert run_pipeline(_options(txt, tmp_path / "txt-build", test_font)).status == "ok"

    pdf = tmp_path / "input.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Vector PDF input text")
    document.save(pdf)
    document.close()
    assert run_pipeline(_options(pdf, tmp_path / "pdf-build", test_font)).status == "ok"


def test_error_report_removes_existing_gcode(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "build"
    output.mkdir()
    (output / "output.gcode").write_text("unsafe stale file", encoding="utf-8")
    _create_docx(source)

    result = run_pipeline(
        PipelineOptions(
            input_path=source,
            font_path=tmp_path / "missing.ttf",
            page="A5",
            size="normal",
            layout_config_path=Path("configs/layout.yaml"),
            machine_config_path=Path("configs/machine.yaml"),
            output_dir=output,
        )
    )

    assert result.status == "error"
    assert not (output / "output.gcode").exists()
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "error"
    assert "Font file does not exist" in report["error"]
