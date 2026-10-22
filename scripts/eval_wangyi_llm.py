"""Can an LLM with Wang Yi's commentary as knowledge see the allegory of the Chu Ci?

Test set: the pilot Chu Ci poems with Wang Yi's images mapped onto them
(data/processed/wangyi/pilot_chuci_wangyi.jsonl, 29 images in 32 poems). For every poem
the commentary on THAT poem is removed from the knowledge base (leave-one-poem-out), so
the model may use Wang Yi's readings of the other poems and its own knowledge, but not
the answer. Recall = share of Wang Yi's images overlapped by a predicted image; Wang Yi
does not comment on every image, so extra predictions are counted, not scored.

Variants
* pipeline: the normal analysis (few_shot+cot+rag+lexicon) with the leave-one-out base;
* allegory: a direct question in the commentary tradition ("which images stand for
  something else — the ruler, worthy or slanderous men, the poet himself?") with the
  top retrieved commentary, and the same question without any commentary.

    python -m scripts.eval_wangyi_llm --variants pipeline:gpt-4o-mini allegory:gpt-4o
"""

import argparse
import json
from pathlib import Path

from openai import OpenAI

from app.core.config import Settings
from app.nlp.corpus import read_corpus
from app.nlp.lexicon import CandidateExtractor
from app.nlp.llm import OpenAIDetector
from app.nlp.rag import KnowledgeBase, format_context

POEMS = Path("data/processed/wangyi/pilot_chuci_wangyi.jsonl")
OUTPUT = Path("data/processed/wangyi/llm_allegory_evaluation.json")
ALLEGORY = (
    "You read the Chu Ci (楚辞) in the commentary tradition of Wang Yi (王逸《楚辞章句》), "
    "where images stand for something else: fragrant plants for worthy men or the poet's "
    "virtue, weeds and foul plants for slanderers, the beautiful woman or deity for the "
    "ruler, fine horses for the worthy, birds for good or evil men, the poet's adornment "
    "for his integrity. List every image in the poem that stands for something else in "
    "this tradition. For each give `text`: the image word(s) copied exactly from the poem "
    "(the shortest form, e.g. 荃 or 美人), and `tenor`: what it stands for, in Chinese. "
    "Do not list plain description. Answer in JSON."
)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"text": {"type": "string"}, "tenor": {"type": "string"}},
                "required": ["text", "tenor"],
            },
        }
    },
    "required": ["images"],
}


def leave_one_out(base: KnowledgeBase, title: str) -> KnowledgeBase:
    return KnowledgeBase([d for d in base.docs if f"《{title}》" not in d.title])


def pipeline(model: str, poem, knowledge, settings) -> tuple[list[tuple[int, int]], dict]:
    detector = OpenAIDetector(
        model,
        settings.openai_api_key,
        strategy="few_shot+cot+rag+lexicon",
        temperature=0.2,
        top_p=0.95,
        extractor=CandidateExtractor(),
        knowledge=knowledge,
        rag_k=8,
    )
    result = detector.analyze(poem.text, "zh")
    usage = result.method.get("usage", {})
    return [(m.start, m.end) for m in result.metaphors], usage


def allegory(model: str, poem, knowledge, client, use_rag: bool):
    context = ""
    if use_rag:
        docs = knowledge.search(poem.text, "zh", k=8)
        context = "\n\nCommentary on other passages (for the tradition, not this poem):\n"
        context += format_context(docs)
    request = dict(
        model=model,
        instructions=ALLEGORY,
        input=f"Poem《{poem.title}》:\n{poem.text}{context}",
        text={
            "format": {"type": "json_schema", "name": "images", "strict": True, "schema": SCHEMA}
        },
        max_output_tokens=4000,
    )
    try:
        response = client.responses.create(**request, temperature=0)
    except Exception as exc:  # reasoning models reject temperature
        if "temperature" not in str(exc).lower():
            raise
        response = client.responses.create(**request)
    images = json.loads(response.output_text)["images"]
    spans = []
    for image in images:
        start = poem.text.find(image["text"]) if image["text"] else -1
        if start >= 0:  # first occurrence; an image not in the poem is dropped
            spans.append((start, start + len(image["text"])))
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return spans, usage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        nargs="+",
        default=[
            "pipeline:gpt-4o-mini",
            "allegory:gpt-4o-mini",
            "allegory:gpt-4o",
            "allegory-norag:gpt-4o",
        ],
    )
    args = parser.parse_args()
    settings = Settings()
    client = OpenAI(api_key=settings.openai_api_key, timeout=120.0, max_retries=2)
    base = KnowledgeBase.load(settings.knowledge_dir)
    poems = read_corpus(POEMS)
    report = {}
    for variant in args.variants:
        kind, model = variant.split(":")
        found = gold = predicted = 0
        tokens = [0, 0]
        for poem in poems:
            knowledge = leave_one_out(base, poem.title)
            if kind == "pipeline":
                spans, usage = pipeline(model, poem, knowledge, settings)
            else:
                spans, usage = allegory(model, poem, knowledge, client, kind == "allegory")
            tokens[0] += usage.get("input_tokens", 0)
            tokens[1] += usage.get("output_tokens", 0)
            predicted += len(spans)
            for g in poem.spans:
                gold += 1
                found += any(s < g.end and e > g.start for s, e in spans)
        report[variant] = {
            "wangyi_images": gold,
            "found": found,
            "recall": found / gold if gold else None,
            "predicted_images": predicted,
            "tokens": tokens,
        }
        print(variant, json.dumps(report[variant]), flush=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
