from pathlib import Path

from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.path_builder import load_path_document, save_path_document


def test_paths_v2_round_trip(tmp_path: Path) -> None:
    source = PathDocument(
        148,
        210,
        [PlotterStroke(0, [Point(1, 2), Point(3, 4)], False, 2, "ё", 1)],
        ["warning"],
        {"pipeline": "ttf-vector"},
    )
    path = tmp_path / "paths.json"
    save_path_document(source, path)
    loaded = load_path_document(path)
    assert loaded == source
    assert "dpi" not in path.read_text(encoding="utf-8")


def test_extracted_asset_provenance_is_byte_stable_between_output_directories(
    tmp_path: Path,
) -> None:
    outputs = []
    for job_name in ("output-A", "output-B"):
        document = PathDocument(
            148,
            210,
            [
                PlotterStroke(
                    0,
                    [Point(1, 2), Point(3, 4)],
                    False,
                    element_id="page-001-image-001",
                    element_type="raster-image",
                    source_path=str(
                        tmp_path
                        / job_name
                        / "extracted-assets"
                        / "image-001-deadbeef.png"
                    ),
                )
            ],
            [],
        )
        target = tmp_path / job_name / "paths.json"
        save_path_document(document, target)
        outputs.append(target.read_bytes())

    assert outputs[0] == outputs[1]
    assert b"asset://image-001-deadbeef.png" in outputs[0]
