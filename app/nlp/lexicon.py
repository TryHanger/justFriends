"""Module B: soft-lexicon candidate extraction (ТЗ п. 3.3, 4 модуль B).

Soft constraints raise recall: every match is only a *candidate* carrier of figurative
meaning. Whether it is used literally or metaphorically is decided by module C.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.schemas.analysis import EntityCandidate

LEXICON_DIR = Path(__file__).resolve().parents[2] / "data/lexicons"
_ALTERNATION = {"к": "г", "қ": "ғ", "п": "б"}
_MIN_STEM = 4


class Lexicon:
    def __init__(self, language: str, entries: list[dict], version: str = "unknown"):
        if language not in {"zh", "kk"}:
            raise ValueError("Lexicon language must be zh or kk")
        self.language, self.version = language, version
        self.entries = entries
        alternatives = []
        for entry in entries:
            for term in [entry["term"], *entry.get("variants", [])]:
                alternatives.append((term, entry))
        if language == "zh":
            # Longest match first so that 明月 wins over 月 at the same position.
            alternatives.sort(key=lambda item: -len(item[0]))
            self._zh = alternatives
        else:
            patterns = []
            for term, entry in alternatives:
                if entry.get("forms"):
                    words = "|".join(
                        re.escape(f) for f in sorted(entry["forms"], key=len, reverse=True)
                    )
                    patterns.append(
                        (re.compile(rf"(?<!\w)(?:{words})(?!\w)", re.IGNORECASE), entry)
                    )
                elif len(term) >= _MIN_STEM:
                    stems = {term}
                    if term[-1] in _ALTERNATION:
                        stems.add(term[:-1] + _ALTERNATION[term[-1]])
                    stem = "|".join(re.escape(s) for s in stems)
                    # Keep the whole word form with affixes, as the annotation guideline requires.
                    patterns.append((re.compile(rf"(?<!\w)(?:{stem})\w*", re.IGNORECASE), entry))
                else:
                    raise ValueError(f"Short Kazakh term {term!r} needs an explicit forms list")
            self._kk = patterns

    @classmethod
    def load(cls, language: str, directory: str | Path | None = None) -> "Lexicon":
        path = Path(directory or LEXICON_DIR) / f"{language}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("language") != language:
            raise ValueError(f"{path}: language field must be {language}")
        return cls(language, data["entries"], data.get("version", "unknown"))

    def lookup(self, word: str) -> dict | None:
        for entry in self.entries:
            if word == entry["term"] or word in entry.get("variants", []):
                return entry
        return None

    def extract(self, text: str) -> list[EntityCandidate]:
        found: list[tuple[int, int, dict]] = []
        if self.language == "zh":
            taken = [False] * len(text)
            for term, entry in self._zh:
                for match in re.finditer(re.escape(term), text):
                    start, end = match.span()
                    if not any(taken[start:end]):
                        taken[start:end] = [True] * (end - start)
                        found.append((start, end, entry))
        else:
            occupied: set[tuple[int, int]] = set()
            for pattern, entry in self._kk:
                for match in pattern.finditer(text):
                    if match.span() not in occupied:
                        occupied.add(match.span())
                        found.append((*match.span(), entry))
        return [
            EntityCandidate(
                text=text[start:end],
                start=start,
                end=end,
                entity_type=entry["entity_type"],
                usage_type=None,
                origin="lexicon",
                lexicon_meaning="; ".join(entry.get("meanings", [])) or None,
            )
            for start, end, entry in sorted(found, key=lambda item: item[:2])
        ]


@lru_cache(maxsize=4)
def default_lexicon(language: str, directory: str | None = None) -> Lexicon:
    return Lexicon.load(language, directory)


class CandidateExtractor:
    """Module B entry point used by every detector."""

    def __init__(self, directory: str | None = None):
        self.directory = directory

    def extract(self, text: str, language: str) -> list[EntityCandidate]:
        return default_lexicon(language, self.directory).extract(text)

    def version(self, language: str) -> str:
        return f"lexicon-{language}-{default_lexicon(language, self.directory).version}"


def merge_candidates(
    model: list[EntityCandidate], lexicon: list[EntityCandidate]
) -> list[EntityCandidate]:
    """Model decisions win at identical boundaries; unmatched lexicon hits stay unclassified."""
    merged = {(c.start, c.end): c for c in lexicon}
    for candidate in model:
        previous = merged.get((candidate.start, candidate.end))
        update = {"origin": "lexicon+model"} if previous else {}
        if previous and previous.lexicon_meaning and not candidate.lexicon_meaning:
            update["lexicon_meaning"] = previous.lexicon_meaning
        merged[(candidate.start, candidate.end)] = candidate.model_copy(update=update)
    return sorted(merged.values(), key=lambda c: (c.start, c.end))
