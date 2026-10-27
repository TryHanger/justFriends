"""Run one LLM annotator over the Kazakh review queue (silver ensemble member).

Failures are recorded per poem instead of aborting the run, so a rerun only needs the
missing ids.

    python -m scripts.kk_ensemble_predict --backend openai --output data/processed/kk_ensemble/gpt-4o-mini.json
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.nlp.__main__ import make_pipeline
from app.nlp.corpus import read_corpus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/kk_ensemble/queue.jsonl")
    parser.add_argument("--backend", required=True)
    parser.add_argument("--strategy")
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    output = Path(args.output)
    done = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    todo = [r for r in read_corpus(args.input) if "error" in done.get(r.id, {"error": 1})]
    pipeline = make_pipeline(args.backend, args.strategy)

    def one(record):
        try:
            return record.id, pipeline.analyze(record.text, record.language).model_dump()
        except Exception as exc:  # noqa: BLE001 - recorded and retried on the next run
            return record.id, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(args.workers) as pool:
        for poem_id, result in pool.map(one, todo):
            done[poem_id] = result
            print(poem_id, "error" if "error" in result else len(result["metaphors"]), flush=True)
    output.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    failed = sum("error" in v for v in done.values())
    print(f"saved {len(done)} poems, failed {failed}")


if __name__ == "__main__":
    main()
