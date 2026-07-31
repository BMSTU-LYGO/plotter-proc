from __future__ import annotations

import math


def analyze_gcode(gcode: str) -> dict[str, object]:
    allowed = {"G0", "G1", "G4", "G21", "G90", "M400", "M84"}
    position: dict[str, float] = {}
    feed: float | None = None
    motion_seconds = 0.0
    dwell_seconds = 0.0
    moves = z_moves = dwell_count = 0
    command_count = 0
    for raw in gcode.splitlines():
        code = raw.split(";", 1)[0].strip()
        if not code:
            continue
        tokens = code.split()
        command = tokens[0]
        if command not in allowed:
            raise ValueError(f"Unsupported generated G-code command: {command}")
        command_count += 1
        values = {token[0]: float(token[1:]) for token in tokens[1:] if len(token) > 1}
        if command == "G4":
            dwell_count += 1
            dwell_seconds += values.get("P", 0) / 1000
        elif command in {"G0", "G1"}:
            if "F" in values:
                feed = values["F"]
            target = dict(position)
            target.update({axis: values[axis] for axis in "XYZ" if axis in values})
            distance = math.sqrt(sum((target.get(a, 0) - position.get(a, 0)) ** 2 for a in "XYZ"))
            if distance and feed:
                motion_seconds += distance / feed * 60
                moves += 1
                z_moves += int("Z" in values)
            position = target
    return {
        "gcode_command_count": command_count,
        "motion_command_count": moves,
        "z_command_count": z_moves,
        "dwell_count": dwell_count,
        "dwell_time_seconds": round(dwell_seconds, 6),
        "ideal_total_time_seconds": round(motion_seconds + dwell_seconds, 6),
    }
