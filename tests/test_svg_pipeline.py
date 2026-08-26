import json
from pathlib import Path

from plotter_processor.document_models import SourceVectorElement
from plotter_processor.pipeline import PipelineOptions, run_pipeline
from plotter_processor.structured_document_reader import read_structured_document


def _drawing(path: Path) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120mm" height="80mm" '
        'viewBox="0 0 120 80">'
        '<g transform="translate(2 3)" fill="none" stroke="black">'
        '<path d="M 0 10 C 20 0 30 20 50 10"/>'
        '<line x1="0" y1="20" x2="40" y2="20"/>'
        '<polyline points="0,30 10,25 20,30"/>'
        '<polygon points="30,25 40,25 35,35"/>'
        '<rect x="50" y="20" width="20" height="15"/>'
        '<circle cx="85" cy="27" r="8"/>'
        '<ellipse cx="105" cy="27" rx="10" ry="6"/>'
        '</g></svg>',
        encoding="utf-8",
    )


def test_svg_is_native_vector_document_with_all_basic_shapes(tmp_path: Path) -> None:
    source = tmp_path / "drawing.svg"
    _drawing(source)

    document = read_structured_document(source)
    vectors = [item for item in document.elements if isinstance(item, SourceVectorElement)]

    assert document.metadata.source_format == "svg"
    assert len(vectors) == 1
    assert len(vectors[0].strokes) == 7
    assert all(stroke.segment_types == ("svg",) for stroke in vectors[0].strokes)
    assert all(stroke.element_type == "svg-vector" for stroke in vectors[0].strokes)


def test_pipeline_runs_svg_to_gcode_without_raster_roundtrip(
    tmp_path: Path, test_font: Path
) -> None:
    source = tmp_path / "drawing.svg"
    _drawing(source)
    output = tmp_path / "output"

    result = run_pipeline(PipelineOptions(
        input_path=source,
        font_path=test_font,
        page="A5",
        size="normal",
        layout_config_path=Path("configs/layout.yaml"),
        machine_config_path=Path("configs/machine.yaml"),
        output_dir=output,
        page_numbers=False,
        images="off",
    ))

    assert result.status == "ok", result.error
    assert (output / "output.gcode").is_file()
    paths = json.loads((output / "paths.json").read_text(encoding="utf-8"))
    assert any("svg" in stroke["segment_types"] for stroke in paths["strokes"])
    assert not (output / "extracted-assets").exists()
