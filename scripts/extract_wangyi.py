"""Distant supervision from Wang Yi's commentary (王逸《楚辭章句》, Eastern Han).

Wang Yi glosses a line and states what an image stands for with explicit markers
(以喻, 喻, 以比, 以譬, 譬, 興): "荃，香草，以喻君也" = the herb 荃 is an image of the ruler.
Each such statement becomes a metaphor span: vehicle = the glossed word found literally
in the line, tenor = what follows the marker. Precision is preferred to recall: a marker
whose vehicle cannot be located in the line is reported, never guessed.

Records are `draft`: the commentary is expert, the extraction is automatic. Lines without
a marker are NOT negatives (Wang Yi does not comment on every image).

    python -m scripts.extract_wangyi --input data/raw/wangyi --output data/processed/wangyi
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.nlp.corpus import Poem, write_corpus
from app.nlp.lexicon import Lexicon

SOURCE = "https://zh.wikisource.org/wiki/楚辭章句"
LICENSE = (
    "Text and commentary in the public domain; Wikisource transcription CC BY-SA 4.0 "
    "(attribution and share-alike required for redistribution)"
)
ENTRY = re.compile(r"\{\{\+\|【(.+?)】\}\}(.*?)(?=\{\{\+\||^=|\Z)", re.S | re.M)
HEADING = re.compile(r"^(={2,3})\s*(.+?)\s*\1\s*$", re.M)
MARKER = re.compile(r"(以喻|以比|以譬|以興|喻|譬|興)")
# "以X喻Y": vehicle named between 以 and the marker.
INSTRUMENTAL = re.compile(r"以([一-鿿]{1,6})(?:喻|比|譬)([^，。；、：]{1,14})")
HAN = re.compile(r"[一-鿿]+")


def clean(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>|<[^>]+>", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}|]*\|([^{}]*)\}\}", r"\1", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    return text.strip()


def tenor_after(sentence: str, position: int) -> str | None:
    tail = re.split(r"[，。；、：！？]", sentence[position:])[0]
    tail = re.sub(r"(也|者|之也|焉)$", "", tail).strip()
    return tail if 1 <= len(tail) <= 14 else None


def gloss_head(sentence: str) -> str | None:
    head = re.split(r"[，：]", sentence, maxsplit=1)[0]
    head = re.sub(r"者$", "", head)
    return head if HAN.fullmatch(head) and len(head) <= 6 else None


def longest_common(head: str, line: str) -> str:
    best = ""
    for i in range(len(head)):
        for j in range(i + len(best) + 1, len(head) + 1):
            if head[i:j] in line:
                best = head[i:j]
            else:
                break
    return best


# "靈以喻君", "女以喻臣": a short noun directly before the marker at the start of a clause.
NOUN_MARKER = re.compile(r"(?:^|[，、])([一-鿿]{1,4})以(?:喻|比|譬)([^，。；、：]{1,14})")
SELF = re.compile(r"以([一-鿿]{1,4})自喻")
# Function words that precede 以喻 without being an image ("故以喻君" = "therefore ...").
NOT_IMAGES = {"故", "是", "此", "亦", "皆", "乃", "所", "蓋", "言", "自", "又", "而", "屈原"}


def strip_tenor(value: str) -> str:
    return re.sub(r"(也|者|之也|焉)$", "", value.strip())


def extract(line: str, commentary: str) -> tuple[list[dict], list[str]]:
    """Return (found spans as dicts, unaligned marker sentences)."""
    found, unaligned = [], []
    sentences = [s for s in re.split(r"(?<=[。；])", commentary) if s.strip()]
    for index, sentence in enumerate(sentences):
        marker = MARKER.search(sentence)
        if not marker:
            continue
        head = gloss_head(sentence)
        if marker.group(1) in {"興", "以興"}:
            # 興 also means "arise / flourish"; trust it only as "X，……以興Y" with a gloss head.
            if marker.group(1) != "以興" or not head or head.startswith("言"):
                continue
        candidates = []  # (vehicle in line, tenor)
        tenor = tenor_after(sentence, marker.end())
        if marker.group(1) == "以興" and (not tenor or len(tenor) < 2):
            continue  # "以興盛" = "thereby flourished", not an image
        self_image = SELF.search(sentence)
        if self_image:
            candidates.append((self_image.group(1), "屈原自身"))
        for match in INSTRUMENTAL.finditer(sentence):
            candidates.append((match.group(1), strip_tenor(match.group(2))))
        for match in NOUN_MARKER.finditer(sentence):
            if match.group(1) in line and match.group(1) not in NOT_IMAGES:
                candidates.append((match.group(1), strip_tenor(match.group(2))))
        if head and not head.startswith("言"):
            # Same-sentence gloss: "荃，香草，以喻君" or "蕙茝皆香草，以喻賢者".
            candidates.append((head if head in line else longest_common(head, line), tenor))
        elif index and not head:
            # "騏驥，駿馬也。以喻賢智": the gloss head of the previous sentence; single
            # characters are too ambiguous across sentences, so require two or more.
            previous = gloss_head(sentences[index - 1])
            if previous and len(previous) >= 2:
                candidates.append((previous, tenor))
        placed = False
        for vehicle, target in candidates:
            if (
                vehicle
                and target
                and vehicle in line
                and vehicle != target
                and vehicle not in NOT_IMAGES
            ):
                found.append({"vehicle": vehicle, "tenor": target, "evidence": sentence.strip()})
                placed = True
                break
        if not placed:
            unaligned.append(sentence.strip())
    return found, unaligned


def poems_from(path: Path) -> list[tuple[str, str, list[tuple[str, str]]]]:
    raw = path.read_text(encoding="utf-8")
    header = re.search(r"\|\s*section\s*=\s*(.+)", raw)
    author = re.search(r"\|\s*author\s*=\s*(.+)", raw)
    work = header.group(1).strip() if header else path.stem
    poems, title = {}, work
    cursor = 0
    for heading in list(HEADING.finditer(raw)) + [None]:
        end = heading.start() if heading else len(raw)
        for match in ENTRY.finditer(raw[cursor:end]):
            poems.setdefault(title, []).append((clean(match.group(1)), clean(match.group(2))))
        if heading:
            name = heading.group(2).strip()
            title = work if name == work else f"{work}·{name}"
            cursor = heading.end()
    who = clean(author.group(1)) if author else "unknown"
    return [(title, who, entries) for title, entries in poems.items() if entries]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lexicon = Lexicon.load("zh")
    records, report = [], {"source": SOURCE, "license": LICENSE, "poems": [], "unaligned": []}
    for path in sorted(args.input.glob("juan*.wiki")):
        for title, author, entries in poems_from(path):
            text_lines, spans, offset = [], [], 0
            for line, commentary in entries:
                found, unaligned = extract(line, commentary)
                for item in found:
                    start = offset + line.index(item["vehicle"])
                    end = start + len(item["vehicle"])
                    if any(start < s["end"] and end > s["start"] for s in spans):
                        continue
                    entry = next(
                        (e for e in lexicon.entries
                         if any(t in item["vehicle"] for t in [e["term"], *e.get("variants", [])])),
                        None,
                    )
                    spans.append(
                        {
                            "text": item["vehicle"], "start": start, "end": end,
                            "label": "metaphor",
                            "source_domain": (entry or {}).get("source_domain", "unknown"),
                            "target_domain": "unknown",
                            "confidence": 1.0,
                            "rationale": f"王逸《楚辭章句》注：{item['evidence']}",
                            "entity": item["vehicle"],
                            "entity_type": (entry or {}).get("entity_type"),
                            "tenor": item["tenor"],
                        }
                    )
                report["unaligned"].extend(
                    {"poem": title, "line": line, "commentary": s} for s in unaligned
                )
                text_lines.append(line)
                offset += len(line) + 1
            text = "\n".join(text_lines)
            key = hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()[:12]
            records.append(
                Poem(
                    id=f"wangyi-{key}", work_id=f"chuci-{title.split('·')[0]}", language="zh",
                    text=text, title=title, author=author, source_url=SOURCE, license=LICENSE,
                    license_verified=True, era="Warring States–Han", genre="chuci",
                    annotation_status="draft" if spans else "unlabeled",
                    annotators=["王逸《楚辭章句》 (автоматическое извлечение)"] if spans else [],
                    spans=sorted(spans, key=lambda s: s["start"]),
                )
            )
            report["poems"].append({"title": title, "lines": len(text_lines), "spans": len(spans)})
    write_corpus(args.output / "chuci_wangyi.jsonl", records)
    report["totals"] = {
        "poems": len(records),
        "lines": sum(p["lines"] for p in report["poems"]),
        "spans": sum(p["spans"] for p in report["poems"]),
        "unaligned_marker_sentences": len(report["unaligned"]),
    }
    (args.output / "extraction_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["totals"], ensure_ascii=False))


if __name__ == "__main__":
    main()
