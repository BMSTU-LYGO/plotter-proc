from pathlib import Path


def test_centerline_corpus_contains_required_regression_glyphs() -> None:
    text = Path("examples/centerline_glyph_corpus.txt").read_text(encoding="utf-8")
    required = set(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789.,!?;:-()«»"
    )
    assert required <= set(text)
    assert len([char for char in text if not char.isspace()]) == len(required)
