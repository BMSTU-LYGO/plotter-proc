from plotter_processor.cli import build_parser, main


def test_parser_exposes_expected_commands() -> None:
    parser = build_parser()

    for command in ("run", "extract", "render", "trace", "gcode", "calibrate"):
        args = parser.parse_args([command, "input.txt"] if command != "calibrate" else [command])
        assert args.command == command


def test_extract_reports_missing_input(capsys) -> None:
    exit_code = main(["extract", "missing.docx"])

    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().out
