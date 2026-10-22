"""Direct usage question on the dictionary set: is word X literal or figurative here?

Unlike the pipeline (find all figures, then check the headword), the model is told which
word to judge, so the score shows whether it understands Kazakh figurative senses at all
(module C), independent of how well it detects figures. Answers are cached per model.
The prompt and schema are shared with stage 2 of the two-stage pipeline (app/nlp/usage.py).

    python -m scripts.eval_kk_usage_direct --models gpt-4o-mini gpt-4o
    python -m scripts.eval_kk_usage_direct --score data/processed/kk_usage/claude_direct.tsv
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.config import Settings
from app.nlp.corpus import read_corpus
from app.nlp.evaluation import cohen_kappa
from app.nlp.usage import INSTRUCTIONS, SCHEMA, direct_question

ROOT = Path("data/processed/kk_usage")


def quotations() -> list[dict]:
    """The balanced sample used for the pipeline evaluation, with the headword marked."""
    ids = {r.id for r in read_corpus(ROOT / "sample.jsonl")}
    records = [
        json.loads(line) for line in (ROOT / "kk_usage_dictionary.jsonl").open(encoding="utf-8")
    ]
    return [r for r in records if r["id"] in ids]


def ask(client, model: str, record: dict) -> str:
    # The same question as stage 2 of the pipeline (app/nlp/usage.py) for one candidate.
    question = direct_question(record["text"], record["start"], record["end"], record["target"])
    request = dict(
        model=model,
        instructions=INSTRUCTIONS,
        input=question,
        text={"format": {"type": "json_schema", "name": "usage", "strict": True, "schema": SCHEMA}},
        max_output_tokens=2000,
    )
    try:
        response = client.responses.create(**request, temperature=0)
    except Exception as exc:  # reasoning models reject temperature
        if "temperature" not in str(exc).lower():
            raise
        response = client.responses.create(**request)
    usage = getattr(response, "usage", None)
    return json.loads(response.output_text)["usage"], (
        getattr(usage, "input_tokens", 0),
        getattr(usage, "output_tokens", 0),
    )


def run(model: str, records: list[dict]) -> Path:
    from openai import OpenAI

    output = ROOT / f"direct-{model}.json"
    done = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    client = OpenAI(api_key=Settings().openai_api_key, timeout=120.0, max_retries=2)
    todo = [r for r in records if r["id"] not in done]

    def one(record):
        try:
            answer, tokens = ask(client, model, record)
            return record["id"], {"usage": answer, "tokens": tokens}
        except Exception as exc:  # noqa: BLE001 - recorded, retried on the next run
            return record["id"], {"error": f"{type(exc).__name__}: {exc}"[:300]}

    with ThreadPoolExecutor(6) as pool:
        for record_id, result in pool.map(one, todo):
            if "error" not in result:
                done[record_id] = result
            else:
                print(record_id, result["error"])
    output.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return output


def score(name: str, answers: dict, records: list[dict]) -> dict:
    gold = {r["id"]: r["usage_type"] == "metaphorical" for r in records}
    pairs = [(gold[i], a == "metaphorical") for i, a in answers.items() if i in gold]
    tp = sum(g and p for g, p in pairs)
    fp = sum(p and not g for g, p in pairs)
    fn = sum(g and not p for g, p in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "model": name,
        "quotations": len(pairs),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if tp else 0.0,
        "accuracy": sum(g == p for g, p in pairs) / len(pairs),
        "cohen_kappa_vs_dictionary": cohen_kappa([g for g, _ in pairs], [p for _, p in pairs]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--score", nargs="*", default=[], help="extra TSV files: id<TAB>usage")
    parser.add_argument("--show", action="store_true", help="print quotations without labels")
    args = parser.parse_args()
    records = quotations()
    if args.show:
        for r in records:
            print(f"{r['id']}\t{r['target']}\t{r['text'].replace(chr(10), ' / ')}")
        return
    report = []
    for model in args.models:
        cached = json.loads(run(model, records).read_text(encoding="utf-8"))
        # The cache may hold answers for quotations of an earlier sample.
        answers = {r["id"]: cached[r["id"]] for r in records if r["id"] in cached}
        result = score(model, {k: v["usage"] for k, v in answers.items()}, records)
        result["tokens"] = [
            sum(v["tokens"][0] for v in answers.values()),
            sum(v["tokens"][1] for v in answers.values()),
        ]
        report.append(result)
    for path in args.score:
        answers = dict(
            line.split("\t")[:2]
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        report.append(score(Path(path).stem, {k: v.strip() for k, v in answers.items()}, records))
    (ROOT / "direct_evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for r in report:
        print(
            f"{r['model']:22} n={r['quotations']} P={r['precision']:.2f} R={r['recall']:.2f} "
            f"F1={r['f1']:.2f} acc={r['accuracy']:.2f} κ={r['cohen_kappa_vs_dictionary']:.2f} "
            f"tokens={r.get('tokens', '-')}"
        )


if __name__ == "__main__":
    main()
