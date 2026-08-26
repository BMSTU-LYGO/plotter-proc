from __future__ import annotations

from dataclasses import dataclass

from plotter_processor.math_expression import MathExpression, normalize_latex_expression


@dataclass(frozen=True, slots=True)
class TextRun:
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class MathRun:
    expression: str
    display_mode: bool
    source_syntax: str
    delimiter: str
    start: int
    end: int
    model: MathExpression | None = None


LatexRun = TextRun | MathRun


def parse_latex_runs(
    text: str,
    *,
    max_expression_length: int = 4000,
    max_elements: int = 500,
) -> list[LatexRun]:
    if max_expression_length < 1 or max_elements < 1:
        raise ValueError("LaTeX parser limits must be positive")
    runs: list[LatexRun] = []
    buffer: list[str] = []
    buffer_start = 0
    index = 0
    formula_count = 0

    def flush_text(end: int) -> None:
        nonlocal buffer_start
        if buffer:
            runs.append(TextRun("".join(buffer), buffer_start, end))
            buffer.clear()
        buffer_start = end

    while index < len(text):
        if text.startswith(r"\$", index):
            if not buffer:
                buffer_start = index
            buffer.append("$")
            index += 2
            continue
        opener, closer, display, syntax = _delimiter_at(text, index)
        if opener is None:
            if not buffer:
                buffer_start = index
            buffer.append(text[index])
            index += 1
            continue
        flush_text(index)
        expression_start = index + len(opener)
        close_index = _find_closer(text, expression_start, closer)
        if close_index < 0:
            raise ValueError(
                f"Unclosed LaTeX delimiter {opener!r} at position {index}"
            )
        expression = text[expression_start:close_index]
        if not expression.strip():
            raise ValueError(f"Empty LaTeX formula at position {index}")
        if len(expression) > max_expression_length:
            raise ValueError(
                f"LaTeX formula at position {index} exceeds max_expression_length "
                f"({max_expression_length})"
            )
        formula_count += 1
        if formula_count > max_elements:
            raise ValueError(f"Document exceeds latex.max_elements_per_document ({max_elements})")
        end = close_index + len(closer)
        runs.append(MathRun(
            expression, display, syntax, opener, index, end,
            normalize_latex_expression(expression, source_syntax=syntax),
        ))
        index = end
        buffer_start = index
    flush_text(len(text))
    return runs


def contains_latex(text: str) -> bool:
    index = 0
    while index < len(text):
        if text.startswith(r"\$", index):
            index += 2
            continue
        opener, _, _, _ = _delimiter_at(text, index)
        if opener is not None:
            return True
        index += 1
    return False


def _delimiter_at(text: str, index: int) -> tuple[str | None, str, bool, str]:
    for opener, closer, display, syntax in (
        ("$$", "$$", True, "dollar-block"),
        (r"\[", r"\]", True, "bracket-block"),
        (r"\(", r"\)", False, "paren-inline"),
        ("$", "$", False, "dollar-inline"),
    ):
        if text.startswith(opener, index):
            return opener, closer, display, syntax
    return None, "", False, ""


def _find_closer(text: str, start: int, closer: str) -> int:
    index = start
    while index <= len(text) - len(closer):
        if text.startswith(closer, index) and not _escaped(text, index):
            return index
        index += 1
    return -1


def _escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1
