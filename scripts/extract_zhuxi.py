"""Expert stanza labels from Zhu Xi's commentary on the Book of Songs (朱熹《詩經集傳》, 1177).

Zhu Xi classifies every stanza of the Shijing as 賦 (direct description), 比 (comparison:
the whole stanza stands for something else) or 興 (evocative image that leads into the
subject), sometimes combined ("興而比也"). The label follows the stanza:
"{{yw|汎彼栢舟、亦汎其流。…}}比也。…". This is the classical expert annotation of
figurative language in Chinese poetry, so it serves as a stanza-level test set:
a model is right on a 比/興 stanza when it marks a figure inside it, and wrong on a 賦
stanza when it does.

Outputs (traditional script kept; `text_simplified` is the OpenCC t2s model input):
* shijing_poems.jsonl: Poem records (unlabeled) for running any backend;
* shijing_zhuxi_stanzas.jsonl: one record per stanza with offsets in the poem and the label;
* extraction_report.json: counts and stanzas whose label could not be read.

    python -m scripts.extract_zhuxi --input data/raw/zhuxi --output data/processed/zhuxi
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from opencc import OpenCC

from app.nlp.corpus import Poem, write_corpus

SOURCE = "https://zh.wikisource.org/wiki/詩經集傳"
LICENSE = (
    "Text and commentary in the public domain; Wikisource transcription CC BY-SA 4.0 "
    "(attribution and share-alike required for redistribution)"
)
HEADING = re.compile(r"^(=+)\s*([^=]+?)\s*\1\s*$", re.M)
STANZA = re.compile(r"\{\{yw\|((?:[^{}]|\{\{annotate\|[^{}]*\}\})*)\}\}")
LABEL = re.compile(r"^\s*○?\s*亦?((?:[賦比興]而)?[賦比興])(?:也|矣)")
# "故以栢舟自比", "以喻…": where the commentary names the image of a 比/興 stanza.
HINT = re.compile(r"以([一-鿿]{1,6}?)(?:自)?(?:比|喻|興)")
t2s = OpenCC("t2s")


def clean(stanza: str) -> str:
    stanza = re.sub(r"\{\{annotate\|[^{}]*\}\}", "", stanza)
    return stanza.replace("○", "").strip()


def poems_from(path: Path):
    """Yield (section, title, [(stanza, label | None, commentary)])."""
    raw = path.read_text(encoding="utf-8")
    headings = list(HEADING.finditer(raw))
    section = ""
    for index, heading in enumerate(headings):
        level, name = len(heading.group(1)), heading.group(2).strip()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(raw)
        if level < 3:
            section = name if level == 2 else section
            continue
        body = raw[heading.end() : end]
        matches = list(STANZA.finditer(body))
        stanzas = []
        for i, match in enumerate(matches):
            tail_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            commentary = body[match.end() : tail_end].strip()
            label = LABEL.match(commentary)
            stanzas.append((clean(match.group(1)), label.group(1) if label else None, commentary))
        if stanzas:
            yield section, name, stanzas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    poems, stanzas, unlabeled = [], [], []
    for path in sorted(args.input.glob("juan*.wiki")):
        for section, title, entries in poems_from(path):
            text = "\n".join(stanza for stanza, _, _ in entries)
            simplified = t2s.convert(text)
            if len(simplified) != len(text):
                raise ValueError(f"t2s changed the length of {title}; offsets would break")
            key = hashlib.sha256(f"{section}\n{title}\n{text}".encode()).hexdigest()[:12]
            poem_id = f"zhuxi-{key}"
            poems.append(
                Poem(
                    id=poem_id,
                    work_id=f"shijing-{section}",
                    language="zh",
                    text=simplified,
                    title=f"{section}·{title}",
                    author="詩經 (無名氏)",
                    source_url=SOURCE,
                    license=LICENSE,
                    license_verified=True,
                    era="Zhou",
                    genre="shijing",
                )
            )
            offset = 0
            for index, (stanza, label, commentary) in enumerate(entries):
                record = {
                    "id": f"{poem_id}-{index}",
                    "poem_id": poem_id,
                    "title": f"{section}·{title}",
                    "volume": path.stem,
                    "stanza": index,
                    "start": offset,
                    "end": offset + len(stanza),
                    "text": stanza,
                    "text_simplified": simplified[offset : offset + len(stanza)],
                    "label": label,
                    "figurative": None if label is None else ("比" in label or "興" in label),
                    "bi": None if label is None else "比" in label,
                    "image_hints": HINT.findall(commentary.split("○")[0])[:3],
                    "commentary": commentary[:400],
                }
                (stanzas if label else unlabeled).append(record)
                offset += len(stanza) + 1
    args.output.mkdir(parents=True, exist_ok=True)
    write_corpus(args.output / "shijing_poems.jsonl", poems)
    with (args.output / "shijing_zhuxi_stanzas.jsonl").open("w", encoding="utf-8") as out:
        for record in stanzas:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = {
        "source": SOURCE,
        "license": LICENSE,
        "poems": len(poems),
        "stanzas": len(stanzas),
        "labels": Counter(s["label"] for s in stanzas),
        "figurative": sum(s["figurative"] for s in stanzas),
        "unlabeled": [{k: s[k] for k in ("title", "stanza", "text")} for s in unlabeled],
    }
    (args.output / "extraction_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "unlabeled"}, ensure_ascii=False))
    print("unlabeled:", len(unlabeled))


if __name__ == "__main__":
    main()
