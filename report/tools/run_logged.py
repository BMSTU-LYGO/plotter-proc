"""Run one audit command and preserve its exact output and metadata."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    root = Path(__file__).resolve().parents[2]
    report = root / "report"
    log_dir = report / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for directory in ("environment", "jobs", "benchmark", "analysis"):
        (report / directory).mkdir(parents=True, exist_ok=True)

    rendered = shlex.join(command)
    started = datetime.now(UTC)
    start = time.monotonic()
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    duration = time.monotonic() - start
    ended = datetime.now(UTC)

    log_text = (
        f"COMMAND: {rendered}\n"
        f"STARTED_UTC: {started.isoformat()}\n"
        f"ENDED_UTC: {ended.isoformat()}\n"
        f"DURATION_SECONDS: {duration:.6f}\n"
        f"EXIT_CODE: {result.returncode}\n\n"
        f"--- STDOUT ---\n{result.stdout}\n"
        f"--- STDERR ---\n{result.stderr}\n"
    )
    (log_dir / f"{args.name}.log").write_text(log_text, encoding="utf-8")
    metadata = {
        "name": args.name,
        "command": command,
        "rendered_command": rendered,
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "duration_seconds": duration,
        "exit_code": result.returncode,
        "stdout_chars": len(result.stdout),
        "stderr_chars": len(result.stderr),
    }
    (log_dir / f"{args.name}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (report / "commands.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
