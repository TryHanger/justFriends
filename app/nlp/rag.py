"""Retrieval-Augmented Generation context (ТЗ п. 2.2.2).

The knowledge base is JSONL in data/knowledge/: MIP/MIPVU guidance, annotation rules,
philological commentaries (e.g. Wang Yi, Zhu Xi on Chu Ci) and lexicon readings.
Retrieval is a dependency-free BM25 over words and CJK character bigrams, so it works in
the base install and is reproducible; retrieved text is passed to the model as data.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data/knowledge"
_CJK = re.compile(r"[㐀-鿿\U00020000-\U0002fa1f]+")
_WORD = re.compile(r"\w+")


class KnowledgeDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    language: str = Field(description="zh, kk or any")
    kind: str = Field(description="guideline, commentary, lexicon or example")
    title: str
    text: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Bibliographic source or URL")
    always: bool = Field(default=False, description="Include in every RAG prompt")


def tokens(text: str) -> list[str]:
    result = []
    for word in _WORD.findall(text.lower()):
        if _CJK.fullmatch(word):
            result.extend(word)
            result.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            result.append(word)
    return result


class KnowledgeBase:
    def __init__(self, docs: list[KnowledgeDoc]):
        if len({d.id for d in docs}) != len(docs):
            raise ValueError("Knowledge document IDs must be unique")
        self.docs = docs
        self._tf = [Counter(tokens(d.title + " " + d.text)) for d in docs]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = sum(self._len) / len(self._len) if docs else 0.0
        df = Counter(term for tf in self._tf for term in tf)
        n = len(docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @classmethod
    def load(cls, directory: str | Path | None = None) -> "KnowledgeBase":
        docs = []
        for path in sorted(Path(directory or KNOWLEDGE_DIR).glob("*.jsonl")):
            for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                if line.strip():
                    try:
                        docs.append(KnowledgeDoc.model_validate_json(line))
                    except ValueError as exc:
                        raise ValueError(f"{path}:{number}: {exc}") from exc
        return cls(docs)

    def search(self, query: str, language: str, k: int = 4) -> list[KnowledgeDoc]:
        if k < 0:
            raise ValueError("k must be nonnegative")
        terms = Counter(tokens(query))
        scored = []
        for index, doc in enumerate(self.docs):
            if doc.always or doc.language not in {language, "any"}:
                continue
            tf, length = self._tf[index], self._len[index]
            score = 0.0
            for term in terms:
                if term in tf:
                    f = tf[term]
                    score += (
                        self._idf[term] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / self._avg))
                    )
            if score > 0:
                scored.append((-score, doc.id, doc))
        fixed = [d for d in self.docs if d.always and d.language in {language, "any"}]
        return fixed + [doc for _, _, doc in sorted(scored)[:k]]


@lru_cache(maxsize=2)
def default_knowledge(directory: str | None = None) -> KnowledgeBase:
    return KnowledgeBase.load(directory)


def format_context(docs: list[KnowledgeDoc], lexicon_hits: list[str] | None = None) -> str:
    parts = [f"[{d.id}] {d.title} ({d.source})\n{d.text}" for d in docs]
    if lexicon_hits:
        parts.append(
            "Lexicon readings (conventional, not proof of metaphor):\n" + "\n".join(lexicon_hits)
        )
    return "\n\n".join(parts)
