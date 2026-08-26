from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class MathValidationStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially-supported"
    INVALID = "invalid"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class MathDiagnostic:
    code: str
    message: str
    position: int | None = None


@dataclass(frozen=True, slots=True)
class MathNode:
    kind: str
    value: str | None = None
    children: tuple[MathNode, ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MathExpression:
    root: MathNode
    normalized: str
    source_syntax: str
    status: MathValidationStatus = MathValidationStatus.SUPPORTED
    diagnostics: tuple[MathDiagnostic, ...] = field(default_factory=tuple)

    @property
    def renderable(self) -> bool:
        return self.status in {
            MathValidationStatus.SUPPORTED,
            MathValidationStatus.PARTIALLY_SUPPORTED,
        }


_FORBIDDEN_COMMANDS = frozenset({
    "documentclass", "usepackage", "input", "include", "includeonly",
    "newcommand", "renewcommand", "providecommand", "def", "edef", "gdef", "xdef",
    "csname", "catcode", "write", "openout", "read", "loop", "repeat",
    "immediate", "special", "directlua", "pdfobj", "pdfxform", "shellescape",
})

_SUPPORTED_COMMAND_KINDS = {
    "frac": "fraction", "dfrac": "fraction", "tfrac": "fraction",
    "sqrt": "root",
    "sum": "n-ary", "prod": "n-ary", "int": "n-ary", "iint": "n-ary",
    "iiint": "n-ary", "oint": "n-ary", "lim": "function",
    "sin": "function", "cos": "function", "tan": "function", "cot": "function",
    "ln": "function", "log": "function", "exp": "function", "min": "function",
    "max": "function",
    "left": "delimiter", "right": "delimiter", "middle": "delimiter",
    "text": "text", "mathrm": "group", "mathbf": "group", "mathit": "group",
    "mathcal": "group", "operatorname": "function",
    "vec": "group", "hat": "group", "bar": "group", "overline": "group",
    "underline": "group", "dot": "group", "ddot": "group",
    "begin": "group", "end": "group",
}

_SYMBOL_COMMANDS = frozenset({
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta",
    "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi",
    "varpi", "rho", "varrho", "sigma", "varsigma", "tau", "upsilon", "phi",
    "varphi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi",
    "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega", "infty", "partial", "nabla",
    "pm", "mp", "times", "div", "cdot", "le", "leq", "ge", "geq", "ne", "neq",
    "approx", "equiv", "sim", "propto", "in", "notin", "subset", "subseteq",
    "supset", "supseteq", "cup", "cap", "setminus", "emptyset", "forall", "exists",
    "neg", "land", "lor", "to", "rightarrow", "leftarrow", "leftrightarrow",
    "Rightarrow", "Leftarrow", "Leftrightarrow", "ldots", "cdots", "vdots", "ddots",
    "wedge", "vee", "mapsto", "perp", "parallel", "mid", "nmid",
    "uparrow", "downarrow", "updownarrow", "Uparrow", "Downarrow", "Updownarrow",
    "hookleftarrow", "hookrightarrow", "longleftarrow", "longrightarrow",
    "Longleftarrow", "Longrightarrow", "Longleftrightarrow",
    "prec", "succ", "preceq", "succeq", "cong", "simeq", "asymp", "doteq",
    "ni", "sqsubset", "sqsubseteq", "sqsupset", "sqsupseteq", "sqcup", "sqcap",
    "uplus", "oplus", "ominus", "otimes", "oslash", "odot",
    "bot", "top", "ast", "star", "circ", "bullet",
    "quad", "qquad", "enspace", ",", ":", ";", "!", " ", "{", "}", "%", "_",
})

_SUPPORTED_COMMANDS = frozenset(_SUPPORTED_COMMAND_KINDS) | _SYMBOL_COMMANDS
_COMMAND_RE = re.compile(r"\\([A-Za-z]+|.)")
_ENVIRONMENT_RE = re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")
_SUPPORTED_ENVIRONMENTS = frozenset({
    "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "cases", "aligned"
})
_FULL_ENVIRONMENT_RE = re.compile(
    r"^\\begin\{([A-Za-z]+)\}(.*)\\end\{\1\}$",
    re.DOTALL,
)
_COMMAND_ALIASES = {"land": "wedge", "lor": "vee"}


def normalize_latex_expression(
    source: str,
    *,
    source_syntax: str = "latex",
) -> MathExpression:
    normalized = " ".join(source.strip().split())
    for alias, canonical in _COMMAND_ALIASES.items():
        normalized = re.sub(
            rf"\\{alias}(?![A-Za-z])",
            lambda _match, command=canonical: f"\\{command}",
            normalized,
        )
    diagnostics: list[MathDiagnostic] = []
    forbidden = False
    unsupported = False

    syntax_error = _syntax_error(normalized)
    if syntax_error is not None:
        diagnostics.append(syntax_error)
        return MathExpression(
            MathNode("row"), normalized, source_syntax,
            MathValidationStatus.INVALID, tuple(diagnostics),
        )

    commands: list[tuple[str, int]] = []
    for match in _COMMAND_RE.finditer(normalized):
        command = match.group(1)
        commands.append((command, match.start()))
        if command in _FORBIDDEN_COMMANDS:
            forbidden = True
            diagnostics.append(MathDiagnostic(
                "forbidden-command", f"Forbidden LaTeX command: \\{command}", match.start()
            ))
        elif command not in _SUPPORTED_COMMANDS and command != "\\":
            unsupported = True
            diagnostics.append(MathDiagnostic(
                "unsupported-command", f"Unsupported LaTeX command: \\{command}", match.start()
            ))

    for match in _ENVIRONMENT_RE.finditer(normalized):
        environment = match.group(2)
        if environment not in _SUPPORTED_ENVIRONMENTS:
            unsupported = True
            diagnostics.append(MathDiagnostic(
                "unsupported-environment",
                f"Unsupported LaTeX environment: {environment}",
                match.start(),
            ))

    status = (
        MathValidationStatus.FORBIDDEN if forbidden
        else MathValidationStatus.PARTIALLY_SUPPORTED if unsupported
        else MathValidationStatus.SUPPORTED
    )
    environment = parse_math_environment(normalized)
    root = (
        MathNode(
            environment[0],
            children=tuple(
                MathNode(
                    "row",
                    children=tuple(
                        MathNode("group", value=cell, children=(_model_row(cell, []),))
                        for cell in row
                    ),
                )
                for row in environment[1]
            ),
        )
        if environment is not None
        else _model_row(normalized, commands)
    )
    return MathExpression(root, normalized, source_syntax, status, tuple(diagnostics))


def visual_math_expression(label: str, *, source_syntax: str = "pdf-visual") -> MathExpression:
    normalized = " ".join(label.strip().split())
    return MathExpression(
        MathNode("row", children=(MathNode("text", normalized),)),
        normalized,
        source_syntax,
    )


def require_renderable(expression: MathExpression) -> MathExpression:
    if expression.status is MathValidationStatus.PARTIALLY_SUPPORTED:
        if expression.source_syntax == "omml" and expression.normalized:
            return expression
        diagnostic = expression.diagnostics[0]
        raise ValueError(diagnostic.message)
    if expression.status in {MathValidationStatus.INVALID, MathValidationStatus.FORBIDDEN}:
        diagnostic = expression.diagnostics[0]
        raise ValueError(diagnostic.message)
    return expression


def parse_math_environment(source: str) -> tuple[str, tuple[tuple[str, ...], ...]] | None:
    match = _FULL_ENVIRONMENT_RE.fullmatch(source.strip())
    if match is None or match.group(1) not in _SUPPORTED_ENVIRONMENTS:
        return None
    rows = tuple(
        tuple(cell.strip() for cell in _split_at_level(row, "&"))
        for row in _split_at_level(match.group(2), r"\\")
    )
    if not rows or any(not row or any(not cell for cell in row) for row in rows):
        return None
    return match.group(1), rows


def _split_at_level(source: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    index = 0
    while index < len(source):
        if source[index] == "{" and (index == 0 or source[index - 1] != "\\"):
            depth += 1
        elif source[index] == "}" and (index == 0 or source[index - 1] != "\\"):
            depth = max(0, depth - 1)
        elif depth == 0 and source.startswith(separator, index):
            parts.append(source[start:index])
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(source[start:])
    return parts


def _syntax_error(source: str) -> MathDiagnostic | None:
    if not source:
        return MathDiagnostic("empty-expression", "Empty LaTeX formula", 0)
    stack: list[tuple[str, int]] = []
    escaped = False
    pairs = {"}": "{", "]": "["}
    for position, character in enumerate(source):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character in "{[":
            stack.append((character, position))
        elif character in "}]":
            if not stack or stack[-1][0] != pairs[character]:
                return MathDiagnostic(
                    "unmatched-delimiter", f"Unmatched LaTeX delimiter: {character}", position
                )
            stack.pop()
    if stack:
        delimiter, position = stack[-1]
        return MathDiagnostic(
            "unclosed-delimiter", f"Unclosed LaTeX delimiter: {delimiter}", position
        )
    return None


def _model_row(source: str, commands: list[tuple[str, int]]) -> MathNode:
    nodes: list[MathNode] = []
    cursor = 0
    for command, position in commands:
        if position > cursor:
            nodes.extend(_plain_nodes(source[cursor:position]))
        kind = _SUPPORTED_COMMAND_KINDS.get(command, "symbol")
        nodes.append(MathNode(kind, f"\\{command}"))
        cursor = position + len(command) + 1
    if cursor < len(source):
        nodes.extend(_plain_nodes(source[cursor:]))
    return MathNode("row", children=tuple(nodes))


def _plain_nodes(value: str) -> list[MathNode]:
    nodes: list[MathNode] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            nodes.append(MathNode("symbols", "".join(buffer)))
            buffer.clear()

    for character in value:
        if character in "+-=<>\u00b1\u00d7\u00f7":
            flush()
            nodes.append(MathNode("operator", character))
        elif character == "_":
            flush()
            nodes.append(MathNode("subscript", character))
        elif character == "^":
            flush()
            nodes.append(MathNode("superscript", character))
        elif character in "()[]|":
            flush()
            nodes.append(MathNode("delimiter", character))
        elif character in "{}":
            flush()
            nodes.append(MathNode("group", character))
        else:
            buffer.append(character)
    flush()
    return nodes
