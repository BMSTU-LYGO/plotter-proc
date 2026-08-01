from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedOMML:
    expression: str
    display_mode: bool
    warnings: tuple[str, ...] = ()


def parse_omml(element: object) -> ParsedOMML:
    warnings: list[str] = []
    expression = _convert(element, warnings).strip()
    if not expression:
        raise ValueError("OMML equation contains no supported mathematical content")
    local = _local_name(getattr(element, "tag", ""))
    return ParsedOMML(expression, local == "oMathPara", tuple(dict.fromkeys(warnings)))


def _convert(element: object, warnings: list[str]) -> str:
    tag = _local_name(getattr(element, "tag", ""))
    children = list(element.iterchildren())
    if tag in {"oMath", "oMathPara", "num", "den", "e", "sup", "sub", "deg", "mr"}:
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
        return rf"\left({body}\right)"
    if tag == "nary":
        symbol = _property_value(element, "chr") or "∑"
        operator = {"∑": r"\sum", "∫": r"\int", "∏": r"\prod"}.get(symbol, symbol)
        sub = _named(element, "sub", warnings, required=False)
        sup = _named(element, "sup", warnings, required=False)
        body = _named(element, "e", warnings, required=False)
        return operator + (rf"_{{{sub}}}" if sub else "") + (rf"^{{{sup}}}" if sup else "") + body
    if tag == "m":
        rows = [_convert(child, warnings) for child in children if _local_name(child.tag) == "mr"]
        return r"\begin{matrix}" + r"\\".join(rows) + r"\end{matrix}"
    if tag in {"fPr", "radPr", "sSupPr", "sSubPr", "sSubSupPr", "naryPr", "dPr", "mPr", "ctrlPr"}:
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


def _property_value(element: object, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name:
            values = list(child.attrib.values())
            return values[0] if values else None
    return None


def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]
