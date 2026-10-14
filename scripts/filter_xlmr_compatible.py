"""Keep only gold records whose boundaries are representable by an XLM-R tokenizer."""

import argparse
import json
from pathlib import Path

from app.nlp.corpus import read_corpus, write_corpus
from app.nlp.xlmr import align_labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--model", default="FacebookAI/xlm-roberta-base")
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)
    accepted, rejected = [], []
    for record in read_corpus(args.input):
        encoded = tokenizer(
            record.text, add_special_tokens=False, return_offsets_mapping=True, verbose=False
        )
        try:
            align_labels(record.text, encoded["offset_mapping"], record.spans)
        except ValueError as exc:
            rejected.append({"id": record.id, "reason": str(exc)})
        else:
            accepted.append(record)
    if not accepted:
        raise ValueError("No XLM-R compatible records remain")
    write_corpus(args.output, accepted)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "model": args.model,
                "accepted": len(accepted),
                "rejected": len(rejected),
                "rejections": rejected,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Accepted {len(accepted)}; rejected {len(rejected)}")


if __name__ == "__main__":
    main()
