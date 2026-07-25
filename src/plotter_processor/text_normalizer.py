import re

from plotter_processor.models import DocumentText

_SUPPORTED_CHARACTER = re.compile(
    r"""[А-Яа-я0-9 .,!?:;\-—()\[\]«»"'№%+=/\\\n]"""
)
_MULTIPLE_SPACES = re.compile(r" {2,}")
_TOO_MANY_NEWLINES = re.compile(r"\n{4,}")


def normalize_text(text: str) -> tuple[str, list[str]]:
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("ё", "е")
        .replace("Ё", "Е")
        .replace("\u00a0", " ")
        .replace("\t", "    ")
    )

    warnings: list[str] = []
    unsupported: set[str] = set()
    characters: list[str] = []
    for character in normalized:
        if _SUPPORTED_CHARACTER.fullmatch(character):
            characters.append(character)
        else:
            characters.append(" ")
            unsupported.add(character)

    normalized = "\n".join(_MULTIPLE_SPACES.sub(" ", line) for line in "".join(characters).split("\n"))
    normalized = _TOO_MANY_NEWLINES.sub("\n\n\n", normalized)

    for character in sorted(unsupported):
        warnings.append(f"Character {character!r} was replaced with a space")

    return normalized, warnings


def normalize_document(document: DocumentText) -> DocumentText:
    text, warnings = normalize_text("\n".join(document.paragraphs))
    return DocumentText(
        paragraphs=text.split("\n"),
        source_path=document.source_path,
        warnings=[*document.warnings, *warnings],
    )
