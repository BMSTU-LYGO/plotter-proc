import re
import unicodedata

from plotter_processor.models import DocumentText

_MULTIPLE_SPACES = re.compile(r" {2,}")
_TOO_MANY_NEWLINES = re.compile(r"\n{4,}")


def normalize_text(text: str) -> tuple[str, list[str]]:
    normalized = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = normalized.replace("\t", "    ")
    warnings: list[str] = []
    characters: list[str] = []
    unsupported: set[str] = set()
    for character in normalized:
        if character in {"\n", "\u00a0"} or character.isprintable():
            characters.append(character)
        else:
            characters.append(" ")
            unsupported.add(character)
    normalized = "\n".join(
        _MULTIPLE_SPACES.sub(" ", line) for line in "".join(characters).split("\n")
    )
    normalized = _TOO_MANY_NEWLINES.sub("\n\n\n", normalized)
    warnings.extend(
        f"Control character U+{ord(char):04X} was replaced with a space"
        for char in sorted(unsupported)
    )
    return normalized, warnings


def normalize_document(document: DocumentText) -> DocumentText:
    text, warnings = normalize_text("\n".join(document.paragraphs))
    return DocumentText(
        paragraphs=text.split("\n"),
        source_path=document.source_path,
        warnings=[*document.warnings, *warnings],
    )
