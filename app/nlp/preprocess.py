"""Language-specific preprocessing before annotation (ТЗ п. 3.1, 3.2).

Applied only to unlabeled records: annotated offsets refer to the exact stored text.
Chinese: NFC (folds CJK compatibility ideographs), configurable variant-character map,
removal of editorial marks (bracketed notes, circled footnote numbers), optional
segmentation into one verse line per row. Traditional and simplified script are kept as is.
Kazakh: NFC and repair of Latin look-alike letters inside Cyrillic words; affixes untouched.
"""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

VARIANTS_PATH = Path(__file__).resolve().parents[2] / "data/normalization/zh_variants.json"
# Editorial notes in brackets typical of digitised editions: （注）〔校〕【按】[1] ［一］.
_EDITORIAL = re.compile(
    r"（[^（）\n]{0,40}）|〔[^〔〕\n]{0,40}〕|【[^【】\n]{0,40}】|\[[^\[\]\n]{0,10}\]|［[^［］\n]{0,10}］"
)
_FOOTNOTES = re.compile(r"[①-⓿❶-➓]")
_VERSE_END = re.compile(r"(?<=[，。！？；：、])")
_LOOKALIKE = str.maketrans(
    {
        "i": "і",
        "I": "І",
        "h": "һ",
        "H": "Һ",
        "a": "а",
        "e": "е",
        "o": "о",
        "c": "с",
        "p": "р",
        "x": "х",
        "y": "у",
        "k": "к",
        "A": "А",
        "E": "Е",
        "O": "О",
        "C": "С",
        "P": "Р",
        "X": "Х",
        "K": "К",
        "M": "М",
        "T": "Т",
        "B": "В",
    }
)
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


@lru_cache(maxsize=1)
def zh_variants(path: str | None = None) -> dict[str, str]:
    file = Path(path) if path else VARIANTS_PATH
    if not file.exists():
        return {}
    data = json.loads(file.read_text(encoding="utf-8"))
    return {k: v for k, v in data["map"].items() if len(k) == 1 and len(v) == 1}


def normalize_zh(
    text: str,
    *,
    remove_editorial: bool = True,
    verse_lines: bool = False,
    variants: dict[str, str] | None = None,
) -> str:
    text = unicodedata.normalize("NFC", text)
    table = zh_variants() if variants is None else variants
    if table:
        text = text.translate(str.maketrans(table))
    if remove_editorial:
        text = _EDITORIAL.sub("", text)
        text = _FOOTNOTES.sub("", text)
    if verse_lines:
        lines = []
        for line in text.split("\n"):
            lines.extend(part.strip() for part in _VERSE_END.split(line) if part.strip())
        text = "\n".join(lines)
    return text


def normalize_kk(text: str) -> str:
    text = unicodedata.normalize("NFC", text)

    def repair(match: re.Match) -> str:
        word = match.group()
        # Only mixed-script words are repaired; Latin-only words (names, quotes) stay.
        return word.translate(_LOOKALIKE) if _CYRILLIC.search(word) else word

    return re.sub(r"\w+", repair, text)


def normalize(text: str, language: str, **options) -> str:
    if language == "zh":
        return normalize_zh(text, **options)
    if language == "kk":
        return normalize_kk(text)
    raise ValueError("language must be zh or kk")
