from plotter_processor.cli import build_parser, main


def test_parser_exposes_expected_commands() -> None:
    parser = build_parser()

    arguments = {
        "run": ["run", "input.txt", "--font", "font.ttf"],
        "svg": ["svg", "input.txt", "--font", "font.ttf"],
        "extract": ["extract", "input.txt"],
        "font-info": ["font-info", "font.ttf"],
        "gcode": ["gcode", "paths.json"],
        "calibrate": ["calibrate"],
    }
    for command, argv in arguments.items():
        args = parser.parse_args(argv)
        assert args.command == command


def test_extract_reports_missing_input(capsys) -> None:
    exit_code = main(["extract", "missing.docx"])

    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().out
