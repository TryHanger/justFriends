"""Corpus importers (ТЗ п. 2.2.1). Imported records are unlabeled and license_verified=false.

A person checks the edition and license of every source before training or publication.
"""

import csv
import hashlib
import json
from pathlib import Path

from app.nlp.corpus import Poem

CHINESE_POETRY_URL = "https://github.com/chinese-poetry/chinese-poetry"


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def _lines(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def import_chinese_poetry(
    paths: list[str | Path],
    *,
    era: str = "unknown",
    genre: str = "poetry",
    revision: str = "unknown",
    prefix: str = "cp",
) -> list[Poem]:
    """Read JSON files of the chinese-poetry repository (e.g. 楚辞/chuci.json, 全唐诗/*.json).

    Supports both `paragraphs` and `content` layouts; `section` (e.g. 九歌) is kept in the title.
    """
    records = []
    for path in paths:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for index, item in enumerate(items):
            text = _lines(item.get("paragraphs") or item.get("content") or item.get("para"))
            if not text:
                continue
            title = str(item.get("title") or item.get("rhythmic") or "").strip()
            if item.get("section"):
                title = f"{item['section']}·{title}" if title else str(item["section"])
            author = str(item.get("author") or "unknown").strip()
            work = _stable_id(author, title, text)
            records.append(
                Poem(
                    id=f"{prefix}-{work}",
                    work_id=f"zh-{_stable_id(author, title)}",
                    language="zh",
                    text=text,
                    title=title or f"{path.stem} #{index + 1}",
                    author=author,
                    source_url=f"{CHINESE_POETRY_URL}/blob/{revision}/{path.as_posix().split('chinese-poetry/')[-1]}",
                    license="MIT (chinese-poetry repository); проверить права на редакцию текста",
                    license_verified=False,
                    era=era,
                    genre=genre,
                )
            )
    return records


METADATA_FIELDS = (
    "file",
    "language",
    "title",
    "author",
    "source_url",
    "license",
    "era",
    "genre",
    "work_id",
)


def import_text_folder(folder: str | Path, metadata_csv: str | Path) -> list[Poem]:
    """Plain-text poems (one file per poem) described by a UTF-8 CSV with METADATA_FIELDS.

    Intended for Kazakh national-corpus and archive exports (эпос, жырау, лирика).
    """
    folder = Path(folder)
    rows = list(csv.DictReader(Path(metadata_csv).read_text(encoding="utf-8-sig").splitlines()))
    missing = set(METADATA_FIELDS) - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"Metadata CSV lacks columns: {sorted(missing)}")
    records = []
    for row in rows:
        text = (folder / row["file"]).read_text(encoding="utf-8-sig")
        records.append(
            Poem(
                id=f"{row['language']}-{_stable_id(row['file'], text)}",
                work_id=row["work_id"]
                or f"{row['language']}-{_stable_id(row['author'], row['title'])}",
                language=row["language"],
                text=text,
                title=row["title"],
                author=row["author"],
                source_url=row["source_url"],
                license=row["license"],
                license_verified=False,
                era=row["era"] or "unknown",
                genre=row["genre"] or "poetry",
            )
        )
    return records
