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


def test_extract_reports_missing_input(capsys) -> None:
    exit_code = main(["extract", "missing.docx"])

    assert exit_code == 1
    assert "does not exist" in capsys.readouterr().out
