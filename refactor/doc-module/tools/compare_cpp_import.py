#!/usr/bin/env python3
"""Compare C++ Document IR with frozen Python DocumentModel snapshots."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = Path(__file__).resolve().parents[1]


def element_type(value: dict) -> str:
    for field, kind in (("styled_paragraphs", "text"), ("image_path", "image"),
                        ("strokes", "vector"), ("expression", "math"),
                        ("cells", "table"), ("start", "line"), ("points", "arrow")):
        if field in value:
            return kind
    raise AssertionError(f"unrecognized Python element: {value['id']}")


def check(case: dict, executable: Path) -> None:
    actual = json.loads(subprocess.check_output([str(executable), str(ROOT / case["input"])], cwd=ROOT))["value"]
    expected = json.loads((MODULE / "golden" / case["id"] / "document.json").read_text())["document"]
    assert len(actual["pages"]) == len(expected["pages"]), "page count"
    for page_index, (cpp, python) in enumerate(zip(actual["pages"], expected["pages"])):
        assert len(cpp["elements"]) == len(python["elements"]), f"page {page_index}: element count"
        for element_index, (left, right) in enumerate(zip(cpp["elements"], python["elements"])):
            location = f"page {page_index}, element {element_index}"
            assert left["type"] == element_type(right), f"{location}: element type"
            assert (left["id"], left["source_order"]) == (right["id"], right["source_order"]), f"{location}: identity"
            if left["type"] == "text":
                strings = ["".join(run["text"] for run in paragraph["runs"]) for paragraph in left["paragraphs"]]
                assert strings == right["paragraphs"], f"{location}: text"
            if left["type"] == "vector":
                contours = left["paths"]
                strokes = right["strokes"]
                assert len(contours) == len(strokes), f"{location}: contour count"
                for contour, stroke in zip(contours, strokes):
                    assert contour["closed"] == stroke["closed"], f"{location}: closed"
                    assert len(contour["points"]) == len(stroke["points"]), f"{location}: point count"
                    for point, golden in zip(contour["points"], stroke["points"]):
                        assert all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(point, (golden["x"], golden["y"]))), f"{location}: geometry"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="built plotter-doc-import executable")
    args = parser.parse_args()
    corpus = json.loads((MODULE / "golden" / "corpus.json").read_text())
    for case in corpus["cases"]:
        if case.get("golden"):
            check(case, args.executable.resolve())
            print(f"{case['id']}: import structure parity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
