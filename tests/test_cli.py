import json
import subprocess
import sys

from plotter_processor.cli import build_parser, main


def test_parser_exposes_expected_commands() -> None:
    parser = build_parser()

    arguments = {
        "run": ["run", "input.txt", "--font", "font.ttf"],
        "svg": ["svg", "input.txt", "--font", "font.ttf"],
        "extract": ["extract", "input.txt"],
        "font-info": ["font-info", "font.ttf"],
        "compile-centerline-font": ["compile-centerline-font", "font.ttf", "--chars", "А"],
        "gcode": ["gcode", "paths.json"],
        "calibrate": ["calibrate"],
    }
    for command, argv in arguments.items():
        args = parser.parse_args(argv)
        assert args.command == command


def test_run_parser_defaults_to_outline_mode() -> None:
    args = build_parser().parse_args(["run", "input.txt", "--font", "font.ttf"])
    assert args.font_mode == "outline"
    assert args.workers == "auto"


def test_run_parser_accepts_explicit_page_worker_count() -> None:
    args = build_parser().parse_args(
        ["run", "input.txt", "--font", "font.ttf", "--workers", "3"]
    )

    assert args.workers == 3


def test_extract_reports_missing_input(capsys) -> None:
    exit_code = main(["extract", "missing.docx"])

    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().out


def test_module_entrypoint_returns_zero_for_success(
    tmp_path, test_font
) -> None:
    source = tmp_path / "input.txt"
    source.write_text("OK", encoding="utf-8")
    output = tmp_path / "success"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plotter_processor",
            "run",
            str(source),
            "--font",
            str(test_font),
            "--output-dir",
            str(output),
            "--no-page-numbers",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads((output / "report.json").read_text(encoding="utf-8"))["status"] == "ok"


def test_module_entrypoint_returns_nonzero_for_failed_job(
    tmp_path, test_font
) -> None:
    source = tmp_path / "missing.txt"
    output = tmp_path / "failure"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plotter_processor",
            "run",
            str(source),
            "--font",
            str(test_font),
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert report["status"] == "error"
    assert "Error:" in result.stdout
