"""Build a reproducible Chinese/Kazakh pilot poetry corpus from public sources.

The output is intentionally *unlabeled*.  It is input for cleaning and human
annotation, not a training set.  Do not mark Kazakh records as license-verified
until the transcription terms have been reviewed by the project team.

Usage:
    python scripts/build_pilot_corpus.py
"""

import argparse
import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "pilot"
GITHUB_RAW = "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master"
GITHUB_WEB = "https://github.com/chinese-poetry/chinese-poetry/blob/master"
CHINESE_SOURCES = (
    ("楚辞", "chuci.json", "Warring States", 50),
    ("诗经", "shijing.json", "Zhou", 50),
    ("全唐诗", "poet.tang.0.json", "Tang", 50),
)
ABAI_INDEX = "https://bilim-all.kz/figure/8?posts=olen"
ABAI_BASE = "https://bilim-all.kz"


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "JustFriendsResearchCorpus/1.0"})
    with urlopen(request, timeout=30) as response:  # nosec B310: curated public URLs above
        return response.read().decode("utf-8")


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha256(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def as_lines(value: list[str]) -> str:
    return "\n".join(line.strip() for line in value if line and line.strip()).strip()


def chinese_records() -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    manifest: list[dict] = []
    seen: set[str] = set()
    for directory, filename, era, limit in CHINESE_SOURCES:
        encoded_directory = quote(directory)
        raw_url = f"{GITHUB_RAW}/{encoded_directory}/{filename}"
        web_url = f"{GITHUB_WEB}/{encoded_directory}/{filename}"
        source_data = json.loads(fetch(raw_url))
        added = 0
        for row in source_data:
            lines = row.get("content") or row.get("paragraphs") or []
            text = as_lines(lines)
            if not text or text in seen:
                continue
            seen.add(text)
            title = str(row.get("title") or "Без названия")
            author = str(row.get("author") or "Неизвестный автор")
            records.append(
                {
                    "id": stable_id("zh", text),
                    "work_id": stable_id("zh-work", text),
                    "language": "zh",
                    "text": text,
                    "title": title,
                    "author": author,
                    "source_url": web_url,
                    "license": "MIT (source repository); premodern source text",
                    "license_verified": True,
                    "era": era,
                    "genre": "poetry",
                    "synthetic": False,
                    "annotation_status": "unlabeled",
                }
            )
            added += 1
            if added == limit:
                break
        if added != limit:
            raise RuntimeError(f"{directory}: expected {limit} texts, collected {added}")
        manifest.append(
            {
                "language": "zh",
                "collection": directory,
                "records": added,
                "source_url": web_url,
                "license": "MIT",
                "license_verified": True,
            }
        )
    return records, manifest


def poem_metadata(page: str) -> tuple[str, str]:
    for block in re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', page, flags=re.DOTALL
    ):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Poem":
            return str(data["name"]).strip(), str(data["author"]["name"]).strip()
    raise ValueError("Poem JSON-LD metadata is missing")


def poem_text(page: str) -> str:
    match = re.search(r'<div class="poem-content">\s*(.*?)\s*</div>', page, flags=re.DOTALL)
    if not match:
        raise ValueError("Poem text block is missing")
    value = re.sub(r"<br\s*/?>", "\n", match.group(1), flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value).replace("\xa0", " ")
    return "\n".join(line.strip() for line in value.splitlines() if line.strip()).strip()


def kazakh_records(limit: int, delay: float) -> tuple[list[dict], list[dict]]:
    index = fetch(ABAI_INDEX)
    paths: list[str] = []
    for path in re.findall(r'href="(/olen/[^"?#]+)"', index):
        if path != "/olen/create" and path not in paths:
            paths.append(path)
    if len(paths) < limit:
        raise RuntimeError(f"Abai index contains only {len(paths)} poem links")

    records: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        page_url = f"{ABAI_BASE}{path}"
        page = fetch(page_url)
        title, author = poem_metadata(page)
        text = poem_text(page)
        if text in seen:
            continue
        seen.add(text)
        records.append(
            {
                "id": stable_id("kk", text),
                "work_id": stable_id("kk-work", text),
                "language": "kk",
                "text": text,
                "title": title,
                "author": author,
                "source_url": page_url,
                "license": (
                    "Public-domain author (Abai Qunanbaiuly, died 1904); "
                    "web transcription terms require verification"
                ),
                "license_verified": False,
                "era": "Late 19th–early 20th century",
                "genre": "poetry",
                "synthetic": False,
                "annotation_status": "unlabeled",
            }
        )
        if len(records) == limit:
            break
        if delay:
            time.sleep(delay)
    if len(records) != limit:
        raise RuntimeError(f"Expected {limit} Kazakh texts, collected {len(records)}")
    return records, [
        {
            "language": "kk",
            "collection": "Abai Qunanbaiuly poems",
            "records": len(records),
            "source_url": ABAI_INDEX,
            "license": "Public-domain author; web transcription terms pending",
            "license_verified": False,
        }
    ]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a public-source pilot poetry corpus")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--kazakh-count", type=int, default=150)
    parser.add_argument("--delay", type=float, default=0.25, help="seconds between Kazakh poem requests")
    args = parser.parse_args()
    if args.kazakh_count < 100 or args.kazakh_count > 150:
        parser.error("--kazakh-count must be between 100 and 150")

    zh, zh_manifest = chinese_records()
    kk, kk_manifest = kazakh_records(args.kazakh_count, args.delay)
    write_jsonl(args.output / "zh_pilot.jsonl", zh)
    write_jsonl(args.output / "kk_pilot.jsonl", kk)
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "records": {"zh": len(zh), "kk": len(kk), "total": len(zh) + len(kk)},
                "sources": [*zh_manifest, *kk_manifest],
                "status": "unlabeled pilot corpus; not approved for model training",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Created {len(zh)} Chinese and {len(kk)} Kazakh records in {args.output}")


if __name__ == "__main__":
    main()
