"""Run from the repository root: python -m app.nlp --help."""

import argparse
import json
import sys
from pathlib import Path

from app.nlp.corpus import clean_corpus, read_corpus, save_json, split_corpus, write_corpus


def main():
    parser = argparse.ArgumentParser(description="Chinese/Kazakh metaphor NLP tools")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--output", default="runs/demo")
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--text-file", required=True)
    analyze.add_argument("--language", choices=["auto", "zh", "kk"], default="auto")
    analyze.add_argument("--backend", choices=["baseline", "openai", "ollama", "xlmr", "hybrid"])
    analyze.add_argument("--output", required=True)
    for name in ("validate", "clean", "split", "label-studio-export"):
        sub = commands.add_parser(name)
        sub.add_argument("input")
        if name != "validate":
            sub.add_argument("--output", required=True)
    imp = commands.add_parser("label-studio-import")
    imp.add_argument("input")
    imp.add_argument("--output", required=True)
    imp.add_argument("--offset-unit", choices=["utf16", "codepoint"], default="utf16")
    imp.add_argument("--adjudicator", help="Use only after human adjudication; otherwise draft")
    train = commands.add_parser("train")
    train.add_argument("--train", required=True)
    train.add_argument("--validation", required=True)
    train.add_argument("--output", required=True)
    train.add_argument("--base-model", default="FacebookAI/xlm-roberta-base")
    train.add_argument("--epochs", type=int, default=3)
    train.add_argument("--batch-size", type=int, default=4)
    attributes = commands.add_parser("train-attributes")
    attributes.add_argument("--train", required=True)
    attributes.add_argument("--output", required=True)
    predict = commands.add_parser("predict")
    predict.add_argument("input")
    predict.add_argument(
        "--backend", choices=["baseline", "openai", "ollama", "xlmr", "hybrid"], default="baseline"
    )
    predict.add_argument("--output", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--gold", required=True)
    evaluate.add_argument("--predictions", required=True)
    evaluate.add_argument("--output", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--queries", required=True, help="JSON array of ComparisonItem")
    compare.add_argument("--candidates", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--k", type=int, default=5)
    retrieval = commands.add_parser("recall-at-k")
    retrieval.add_argument("--relevance", required=True)
    retrieval.add_argument("--rankings", required=True)
    retrieval.add_argument("--k", type=int, default=5)
    agreement = commands.add_parser("agreement")
    agreement.add_argument("first")
    agreement.add_argument("second")
    agreement.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"Error: {exc}\n")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def make_pipeline(backend=None):
    from app.core.config import Settings
    from app.nlp.pipeline import build_pipeline

    settings = Settings(**({"nlp_backend": backend} if backend else {}))
    return build_pipeline(settings)


def run(args):
    command = args.command
    if command == "demo":
        from app.nlp.baseline import LexicalDetector
        from app.nlp.evaluation import evaluate

        records = read_corpus(Path(__file__).resolve().parents[2] / "data/examples/synthetic.jsonl")
        predictions = {r.id: LexicalDetector().analyze(r.text, r.language) for r in records}
        output = Path(args.output)
        save_json(output / "predictions.json", {k: v.model_dump() for k, v in predictions.items()})
        save_json(output / "metrics.json", evaluate(records, predictions))
        print(f"Synthetic demo only. Outputs: {output.resolve()}")
    elif command == "validate":
        records = read_corpus(args.input)
        print(
            f"Valid: {len(records)} poems; gold={sum(r.annotation_status == 'gold' for r in records)}"
        )
    elif command == "clean":
        records, report = clean_corpus(read_corpus(args.input))
        write_corpus(args.output, records)
        save_json(str(args.output) + ".duplicates.json", report)
    elif command == "split":
        for name, records in split_corpus(read_corpus(args.input)).items():
            write_corpus(Path(args.output) / f"{name}.jsonl", records)
    elif command == "label-studio-export":
        from app.nlp.annotation import export_tasks

        save_json(args.output, export_tasks(read_corpus(args.input)))
    elif command == "label-studio-import":
        from app.nlp.annotation import import_tasks

        write_corpus(
            args.output,
            import_tasks(
                load_json(args.input), offset_unit=args.offset_unit, adjudicator=args.adjudicator
            ),
        )
    elif command == "analyze":
        # Preserve CRLF: offsets must refer to exactly the loaded text.
        with open(args.text_file, encoding="utf-8", newline="") as stream:
            text = stream.read()
        result = make_pipeline(args.backend).analyze(text, args.language)
        save_json(args.output, result.model_dump())
    elif command == "predict":
        pipeline = make_pipeline(args.backend)
        predictions = {
            r.id: pipeline.analyze(r.text, r.language).model_dump() for r in read_corpus(args.input)
        }
        save_json(args.output, predictions)
    elif command == "evaluate":
        from app.nlp.evaluation import evaluate
        from app.schemas.analysis import AnalysisResult

        predictions = {
            k: AnalysisResult.model_validate(v) for k, v in load_json(args.predictions).items()
        }
        save_json(args.output, evaluate(read_corpus(args.gold), predictions))
    elif command == "train":
        from app.nlp.training import train_xlmr

        train_xlmr(
            args.train,
            args.validation,
            args.output,
            model_name=args.base_model,
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
    elif command == "train-attributes":
        from app.nlp.attributes import train_attributes

        train_attributes(read_corpus(args.train), args.output)
    elif command == "compare":
        from app.core.config import Settings
        from app.nlp.comparison import CrossLanguageMatcher
        from app.schemas.comparison import ComparisonItem

        result = CrossLanguageMatcher(Settings().embedding_model).compare(
            [ComparisonItem.model_validate(x) for x in load_json(args.queries)],
            [ComparisonItem.model_validate(x) for x in load_json(args.candidates)],
            args.k,
        )
        save_json(args.output, result.model_dump())
    elif command == "recall-at-k":
        from app.nlp.evaluation import recall_at_k

        print(recall_at_k(load_json(args.relevance), load_json(args.rankings), args.k))
    elif command == "agreement":
        from app.nlp.evaluation import annotation_agreement

        save_json(
            args.output, annotation_agreement(read_corpus(args.first), read_corpus(args.second))
        )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
