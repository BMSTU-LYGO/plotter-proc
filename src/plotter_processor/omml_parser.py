from __future__ import annotations

from dataclasses import dataclass, replace

from plotter_processor.math_expression import (
    MathDiagnostic,
    MathExpression,
    MathNode,
    MathValidationStatus,
    normalize_latex_expression,
)


@dataclass(frozen=True, slots=True)
class ParsedOMML:
    expression: str
    display_mode: bool
    warnings: tuple[str, ...] = ()
    model: MathExpression | None = None


def parse_omml(element: object) -> ParsedOMML:
    warnings: list[str] = []
    expression = _convert(element, warnings).strip()
    if not expression:
        raise ValueError("OMML equation contains no supported mathematical content")
    local = _local_name(getattr(element, "tag", ""))
    normalized = normalize_latex_expression(expression, source_syntax="omml")
    unique_warnings = tuple(dict.fromkeys(warnings))
    model = replace(
        normalized,
        root=_model(element),
        status=(
            MathValidationStatus.PARTIALLY_SUPPORTED
            if unique_warnings else normalized.status
        ),
        diagnostics=(
            *normalized.diagnostics,
            *(MathDiagnostic("omml-warning", warning) for warning in unique_warnings),
        ),
    )
    return ParsedOMML(
        expression,
        local == "oMathPara",
        unique_warnings,
        model,
    )


def _convert(element: object, warnings: list[str]) -> str:
    tag = _local_name(getattr(element, "tag", ""))
    children = list(element.iterchildren())
    if tag in {
        "oMath", "oMathPara", "num", "den", "e", "sup", "sub", "deg", "mr",
        "funcName", "lim", "box", "borderBox",
    }:
        return "".join(_convert(child, warnings) for child in children)
    if tag in {"r", "t"}:
        text = getattr(element, "text", None) or ""
        return text + "".join(_convert(child, warnings) for child in children)
    if tag == "f":
        return rf"\frac{{{_named(element, 'num', warnings)}}}{{{_named(element, 'den', warnings)}}}"
    if tag == "sSup":
        return rf"{{{_named(element, 'e', warnings)}}}^{{{_named(element, 'sup', warnings)}}}"
    if tag == "sSub":
        return rf"{{{_named(element, 'e', warnings)}}}_{{{_named(element, 'sub', warnings)}}}"
    if tag == "sSubSup":
        return (
            rf"{{{_named(element, 'e', warnings)}}}_{{{_named(element, 'sub', warnings)}}}"
            rf"^{{{_named(element, 'sup', warnings)}}}"
        )
    if tag in {"rad", "sRad"}:
        degree = _named(element, "deg", warnings, required=False)
        body = _named(element, "e", warnings)
        return rf"\sqrt[{degree}]{{{body}}}" if degree else rf"\sqrt{{{body}}}"
    if tag == "d":
        body = _named(element, "e", warnings)
        begin = _property_value(element, "begChr") or "("
        end = _property_value(element, "endChr") or ")"
        if body.startswith(r"\begin{matrix}") and body.endswith(r"\end{matrix}"):
            environment = {
                ("(", ")"): "pmatrix",
                ("[", "]"): "bmatrix",
                ("{", "}"): "Bmatrix",
                ("|", "|"): "vmatrix",
                ("‖", "‖"): "Vmatrix",
            }.get((begin, end))
            if environment is not None:
                inner = body[len(r"\begin{matrix}") : -len(r"\end{matrix}")]
                return rf"\begin{{{environment}}}{inner}\end{{{environment}}}"
        return rf"\left{_latex_delimiter(begin)}{body}\right{_latex_delimiter(end)}"
    if tag == "nary":
        symbol = _property_value(element, "chr") or "∑"
        operator = {
            "∑": r"\sum", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint",
            "∏": r"\prod",
        }.get(symbol, symbol)
        sub = _named(element, "sub", warnings, required=False)
        sup = _named(element, "sup", warnings, required=False)
        body = _named(element, "e", warnings, required=False)
        return operator + (rf"_{{{sub}}}" if sub else "") + (rf"^{{{sup}}}" if sup else "") + body
    if tag == "m":
        rows = [_matrix_row(child, warnings) for child in children if _local_name(child.tag) == "mr"]
        return r"\begin{matrix}" + r"\\".join(rows) + r"\end{matrix}"
    if tag == "eqArr":
        rows = [
            _convert(child, warnings) for child in children if _local_name(child.tag) == "e"
        ]
        return r"\begin{aligned}" + r"\\".join(rows) + r"\end{aligned}"
    if tag == "func":
        name = _named(element, "funcName", warnings)
        argument = _named(element, "e", warnings)
        command = name.strip()
        known = {"sin", "cos", "tan", "cot", "ln", "log", "exp", "min", "max", "lim"}
        rendered_name = rf"\{command}" if command in known else rf"\operatorname{{{command}}}"
        return f"{rendered_name} {argument}"
    if tag == "acc":
        accent = _property_value(element, "chr") or "̂"
        command = {
            "̂": "hat", "^": "hat", "¯": "bar", "̅": "bar", "→": "vec",
            "˙": "dot", "̇": "dot", "¨": "ddot", "̈": "ddot",
        }.get(accent, "hat")
        return rf"\{command}{{{_named(element, 'e', warnings)}}}"
    if tag in {"limLow", "limUpp"}:
        body = _named(element, "e", warnings)
        limit = _named(element, "lim", warnings)
        marker = "_" if tag == "limLow" else "^"
        return rf"{{{body}}}{marker}{{{limit}}}"
    if tag == "groupChr":
        return rf"\overline{{{_named(element, 'e', warnings)}}}"
    if tag in {
        "fPr", "radPr", "sSupPr", "sSubPr", "sSubSupPr", "naryPr", "dPr", "mPr",
        "eqArrPr", "funcPr", "accPr", "limLowPr", "limUppPr", "groupChrPr",
        "boxPr", "borderBoxPr", "ctrlPr", "rPr", "argPr",
    }:
        return ""
    warnings.append(f"omml_unsupported_node:{tag or 'unknown'}")
    return "".join(_convert(child, warnings) for child in children)


def _named(
    element: object, name: str, warnings: list[str], *, required: bool = True
) -> str:
    for child in element.iterchildren():
        if _local_name(child.tag) == name:
            return _convert(child, warnings)
    if required:
        warnings.append(f"omml_missing_node:{name}")
    return ""


def _matrix_row(element: object, warnings: list[str]) -> str:
    cells = [
        _convert(child, warnings)
        for child in element.iterchildren()
        if _local_name(child.tag) == "e"
    ]
    return "&".join(cells) if cells else _convert(element, warnings)


def _latex_delimiter(value: str) -> str:
    return {"{": r"\{", "}": r"\}", "": "."}.get(value, value)


def _model(element: object) -> MathNode:
    tag = _local_name(getattr(element, "tag", ""))
    children = list(element.iterchildren())
    meaningful = tuple(
        _model(child) for child in children if not _local_name(child.tag).endswith("Pr")
    )
    if tag in {"oMath", "oMathPara"}:
        flattened = tuple(
            grandchild
            for child in meaningful
            for grandchild in (child.children if child.kind == "row" else (child,))
        )
        return MathNode("row", children=flattened)
    if tag in {"e", "num", "den", "sup", "sub", "deg"}:
        return MathNode("row", children=meaningful)
    if tag in {"r", "t"}:
        return MathNode("symbols", getattr(element, "text", None) or "", meaningful)
    kinds = {
        "f": "fraction",
        "rad": "root", "sRad": "root",
        "sSup": "superscript", "sSub": "subscript", "sSubSup": "sub-sup",
        "nary": "n-ary", "d": "delimiter", "func": "function", "acc": "accent",
        "limLow": "limit", "limUpp": "limit", "m": "matrix", "mr": "row",
        "eqArr": "equation-array", "groupChr": "group", "box": "group",
        "borderBox": "group",
    }
    return MathNode(kinds.get(tag, "group"), tag, meaningful)


def _property_value(element: object, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name:
            values = list(child.attrib.values())
            return values[0] if values else None
    return None


def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]
