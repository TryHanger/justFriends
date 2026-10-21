"""Silver annotation of the Kazakh review queue by an ensemble of models.

There is no native-speaker annotator, so independent model annotators label the same
poems: an LLM run through the pipeline (scripts/kk_ensemble_predict.py) and Claude's
hand annotation (claude_annotations.tsv, made without seeing any model output). This
script turns both into corpora, measures their agreement and splits the result into

* consensus.jsonl: figures both annotators found (character overlap); silver, never gold;
* a Label Studio file with every poem where they disagree, one prediction per annotator,
  so a human only checks the disputed places.

    python -m scripts.kk_ensemble
"""

import json
import re
from collections import Counter
from pathlib import Path

from app.nlp.contracts import ModelSpan
from app.nlp.corpus import Poem, read_corpus, write_corpus
from app.nlp.evaluation import annotation_agreement, cohen_kappa
from app.nlp.llm import locate_tenor
from app.nlp.quality import overlap_matches

ROOT = Path("data/processed/kk_ensemble")
LS_OUTPUT = Path("data/processed/labelstudio/04_kk_ensemble_disagreements.json")
ENTITY_TYPES = {
    "plant": "plant",
    "animal": "animal",
    "body": "body",
    "person": "person",
    "object": "artifact",
    "fire": "natural_phenomenon",
    "water": "natural_phenomenon",
    "light": "natural_phenomenon",
    "nature": "natural_phenomenon",
}


def find(text: str, span: str, occurrence: int) -> tuple[int, int]:
    # Letters only: footnote digits are glued to words ("рәушан1").
    pattern = re.compile(r"(?<![^\W\d_])" + re.escape(span) + r"(?![^\W\d_])")
    matches = list(pattern.finditer(text))
    if len(matches) < occurrence:
        raise ValueError(f"{span!r} occurrence {occurrence} not found")
    match = matches[occurrence - 1]
    return match.start(), match.end()


def claude_corpus(queue: list[Poem]) -> list[Poem]:
    spans: dict[int, list[ModelSpan]] = {}
    for line in (ROOT / "claude_annotations.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        idx, span, label, source, target, tenor, ground, sentiment = line.split("|")
        text = queue[int(idx)].text
        span, _, occurrence = span.partition("@")
        start, end = find(text, span, int(occurrence or 1))
        tenor_bounds = locate_tenor(text, tenor, start, end) if tenor else None
        spans.setdefault(int(idx), []).append(
            ModelSpan(
                text=span,
                start=start,
                end=end,
                label=label,
                source_domain=source,
                target_domain=target,
                confidence=0.8,
                rationale="Независимая разметка Claude (Opus 5.5).",
                entity=span,
                entity_type=ENTITY_TYPES.get(source, "abstract"),
                sentiment=sentiment,
                tenor=tenor or None,
                ground=ground or None,
                tenor_start=tenor_bounds[0] if tenor_bounds else None,
                tenor_end=tenor_bounds[1] if tenor_bounds else None,
            )
        )
    return [annotated(r, spans.get(i, []), "claude-opus-5-5") for i, r in enumerate(queue)]


def llm_corpus(queue: list[Poem], path: Path, name: str) -> list[Poem]:
    predictions = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for record in queue:
        result = predictions[record.id]
        if "error" in result:
            raise ValueError(f"{name} failed on {record.id}; rerun kk_ensemble_predict")
        records.append(
            annotated(record, [ModelSpan.model_validate(m) for m in result["metaphors"]], name)
        )
    return records


def annotated(record: Poem, spans: list[ModelSpan], name: str) -> Poem:
    return record.model_copy(
        update={
            "spans": sorted(spans, key=lambda s: s.start),
            "annotation_status": "draft",
            "annotators": [name],
        }
    )


def regions(prefix: str, spans: list[ModelSpan]) -> list[dict]:
    result = []
    for i, span in enumerate(spans):
        region = f"{prefix}-{i}"

        def item(kind, name, value, region=region):
            return {
                "id": region,
                "type": kind,
                "from_name": name,
                "to_name": "poem",
                "value": value,
            }

        result.append(
            item(
                "labels",
                "figure",
                {
                    "start": span.start,
                    "end": span.end,
                    "text": span.text,
                    "labels": [span.label],
                },
            )
        )
        for name in ("source_domain", "target_domain", "sentiment"):
            if getattr(span, name):
                result.append(item("choices", name, {"choices": [getattr(span, name)]}))
        for name in ("semantic_label", "tenor", "ground"):
            if getattr(span, name):
                result.append(item("textarea", name, {"text": [getattr(span, name)]}))
    return result


def compare(first: list[Poem], second: list[Poem]) -> dict:
    """Boundary-tolerant agreement: figures that overlap count as the same figure."""
    matched = only_first = only_second = 0
    labels, sources, targets = [], [], []
    for a, b in zip(first, second, strict=True):
        pairs = overlap_matches(a.spans, b.spans)
        matched += len(pairs)
        only_first += len(a.spans) - len(pairs)
        only_second += len(b.spans) - len(pairs)
        for x, y in pairs:
            labels.append((x.label, y.label))
            sources.append((x.source_domain, y.source_domain))
            targets.append((x.target_domain, y.target_domain))

    def kappa(rows):
        return {
            "agreement": sum(x == y for x, y in rows) / len(rows) if rows else None,
            "cohen_kappa": cohen_kappa(*map(list, zip(*rows, strict=True))) if rows else None,
        }

    total = 2 * matched + only_first + only_second
    return {
        "figures": {"first": matched + only_first, "second": matched + only_second},
        "overlap_matched": matched,
        "only_first": only_first,
        "only_second": only_second,
        "overlap_dice": 2 * matched / total if total else None,
        "label_on_matched": kappa(labels),
        "source_domain_on_matched": kappa(sources),
        "target_domain_on_matched": kappa(targets),
    }


def main() -> None:
    queue = read_corpus(ROOT / "queue.jsonl")
    annotators = {
        "claude-opus-5-5": claude_corpus(queue),
        "openai:gpt-4o-mini": llm_corpus(queue, ROOT / "gpt-4o-mini.json", "openai:gpt-4o-mini"),
    }
    for name, records in annotators.items():
        write_corpus(ROOT / f"{name.split(':')[-1]}.jsonl", records)
    names = list(annotators)
    first, second = (annotators[n] for n in names)
    report = {
        "annotators": names,
        "poems": len(queue),
        "status": "silver: model annotators only, not gold",
        "overlap": compare(first, second),
        "strict": annotation_agreement(first, second),
    }

    consensus, tasks = [], []
    for a, b in zip(first, second, strict=True):
        pairs = overlap_matches(a.spans, b.spans)
        consensus.append(
            a.model_copy(
                update={
                    "spans": sorted((x for x, _ in pairs), key=lambda s: s.start),
                    "annotators": ["ensemble: " + " + ".join(names)],
                }
            )
        )
        disputed = len(a.spans) + len(b.spans) - 2 * len(pairs)
        if disputed:
            data = a.model_dump(exclude={"spans", "candidates", "annotators", "annotation_status"})
            data.update(
                annotation_status="unlabeled",
                review_queue="kk-ensemble-disagreements-v1",
                review_note=(
                    f"Модели совпали в {len(pairs)} местах, расходятся в {disputed}. "
                    "Подсказки — от двух моделей; выберите вкладку и исправьте."
                ),
                disputed=disputed,
            )
            tasks.append(
                {
                    "data": data,
                    "predictions": [
                        {"model_version": names[0], "result": regions("claude", a.spans)},
                        {"model_version": names[1], "result": regions("gpt", b.spans)},
                    ],
                }
            )
    tasks.sort(key=lambda t: -t["data"]["disputed"])
    write_corpus(ROOT / "consensus.jsonl", consensus)
    LS_OUTPUT.write_text(json.dumps(tasks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report["consensus_figures"] = sum(len(r.spans) for r in consensus)
    report["consensus_labels"] = Counter(s.label for r in consensus for s in r.spans)
    report["label_studio_tasks"] = len(tasks)
    (ROOT / "agreement.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
