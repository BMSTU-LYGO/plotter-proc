from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_latex_university_corpus.py",
    "tests/test_latex_environments.py",
    "tests/test_latex_layout.py",
    "tests/test_latex_centerline_quality.py",
    "tests/test_omml_corpus.py",
    "tests/test_pdf_math_detector.py",
    "tests/test_pdf_document_reader.py",
    "tests/test_svg_pipeline.py",
    "tests/test_docx_shapes.py",
    "tests/test_image_vectorizer.py",
    "tests/test_gcode_exporter.py",
    "tests/test_update_18_corpus.py",
)


def main() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TESTS],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
