"""Project Wang Yi's commentary spans onto the simplified-script Chu Ci pilot texts.

Wang Yi's edition is traditional script with its own punctuation; the pilot comes from
chinese-poetry in simplified script. A span is transferred only when its line and its
vehicle are found unambiguously after OpenCC t2s conversion. Output records are `draft`
and also serve as expert-backed suggestions for Label Studio.

    python -m scripts.map_wangyi_to_pilot
"""

import json
import re
from pathlib import Path

from opencc import OpenCC

from app.nlp.corpus import Poem, read_corpus, write_corpus

PUNCT = re.compile(r"[，。；：、！？「」『』《》\s]")
t2s = OpenCC("t2s")


def key(title: str) -> str:
    return t2s.convert(title).split("·")[-1].strip()


def locate(text: str, line: str, vehicle: str) -> tuple[int, int] | None:
    core = PUNCT.sub("", t2s.convert(line))
    anchor = core[:4]
    if len(anchor) < 3 or text.count(anchor) != 1:
        return None
    window_start = text.index(anchor)
    window = text[window_start : window_start + len(line) + 6]
    target = t2s.convert(vehicle)
    if window.count(target) != 1:
        return None
    start = window_start + window.index(target)
    return start, start + len(target)


def main() -> None:
    wangyi = {key(r.title): r for r in read_corpus("data/processed/wangyi/chuci_wangyi.jsonl")}
    tasks = json.loads(Path("data/processed/pilot/label-studio-zh-gpt.json").read_text(encoding="utf-8"))
    records, stats = [], {"poems": 0, "spans": 0, "mapped": 0, "unmapped": []}
    for task in tasks:
        data = task["data"]
        source = wangyi.get(data["title"])
        if data["era"] != "Warring States" or source is None:
            continue
        stats["poems"] += 1
        spans = []
        for span in source.spans:
            stats["spans"] += 1
            line_start = source.text.rfind("\n", 0, span.start) + 1
            line_end = source.text.find("\n", span.end)
            line = source.text[line_start : line_end if line_end >= 0 else None]
            bounds = locate(data["text"], line, span.text)
            if bounds is None or any(bounds[0] < s["end"] and bounds[1] > s["start"] for s in spans):
                stats["unmapped"].append({"title": data["title"], "vehicle": span.text, "line": line})
                continue
            stats["mapped"] += 1
            spans.append(
                {
                    **span.model_dump(include={"label", "source_domain", "target_domain",
                                               "confidence", "rationale", "entity_type"}),
                    "text": data["text"][bounds[0] : bounds[1]],
                    "start": bounds[0],
                    "end": bounds[1],
                    "entity": data["text"][bounds[0] : bounds[1]],
                    "tenor": t2s.convert(span.tenor),
                }
            )
        record = {**data, "spans": sorted(spans, key=lambda s: s["start"])}
        record.update(
            annotation_status="draft" if spans else "unlabeled",
            annotators=["王逸《楚辭章句》 (автоматическое извлечение)"] if spans else [],
        )
        records.append(Poem.model_validate(record))
    write_corpus("data/processed/wangyi/pilot_chuci_wangyi.jsonl", records)
    Path("data/processed/wangyi/pilot_mapping_report.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print({k: v for k, v in stats.items() if k != "unmapped"}, "unmapped:", len(stats["unmapped"]))


if __name__ == "__main__":
    main()
