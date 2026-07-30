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
