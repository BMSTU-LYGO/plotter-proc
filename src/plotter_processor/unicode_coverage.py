from __future__ import annotations

import unicodedata

COVERAGE_GROUPS: dict[str, str] = {
    "basic_math": "±×÷√∞",
    "relations": "=≠≤≥≈",
    "operators": "+-±×÷∑",
    "calculus": "∑∫√∂∇∞",
    "greek_lower": "αβγδεθλμπσφω",
    "greek_upper": "ΓΔΘΛΞΠΣΦΨΩ",
    "superscripts": "⁰¹²³⁴⁵⁶⁷⁸⁹",
    "arrows": "←↑→↓↔⇐⇒⇔",
}
MATH_GROUPS = ("basic_math", "relations", "operators", "calculus", "greek_lower", "superscripts")


def inspect_coverage(cmap: dict[int, str], group: str) -> dict[str, object]:
    names = MATH_GROUPS if group == "math" else (group,)
    unknown = [name for name in names if name not in COVERAGE_GROUPS]
    if unknown:
        raise ValueError(f"Unknown Unicode coverage group: {unknown[0]}")
    chars = "".join(dict.fromkeys("".join(COVERAGE_GROUPS[name] for name in names)))
    symbols = [
        {
            "char": char,
            "codepoint": f"U+{ord(char):04X}",
            "name": unicodedata.name(char, "UNKNOWN"),
            "supported": ord(char) in cmap,
            "glyph_name": cmap.get(ord(char)),
        }
        for char in chars
    ]
    supported = sum(bool(item["supported"]) for item in symbols)
    return {
        "group": group,
        "supported": supported,
        "total": len(symbols),
        "missing": [item for item in symbols if not item["supported"]],
        "symbols": symbols,
    }
