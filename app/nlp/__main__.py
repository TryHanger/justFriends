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
    analyze.add_argument(
        "--backend", choices=["baseline", "openai", "anthropic", "ollama", "hf", "xlmr", "hybrid"]
    )
    analyze.add_argument("--strategy", help="zero_shot or few_shot, cot, rag, lexicon joined by +")
    analyze.add_argument("--output", required=True)
    for name in ("validate", "clean", "split", "label-studio-export"):
        sub = commands.add_parser(name)
        sub.add_argument("input")
        if name != "validate":
            sub.add_argument("--output", required=True)
        if name == "clean":
            sub.add_argument("--verse-lines", action="store_true", help="zh: one verse per line")
            sub.add_argument("--keep-editorial", action="store_true")
        if name == "label-studio-export":
            sub.add_argument(
                "--prefill-candidates",
                action="store_true",
                help="soft-lexicon candidates as predictions (second stage only)",
            )
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
        "--backend",
        choices=["baseline", "openai", "anthropic", "ollama", "hf", "xlmr", "hybrid"],
        default="baseline",
    )
    predict.add_argument("--strategy")
    predict.add_argument("--output", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--gold", required=True)
    evaluate.add_argument("--predictions", required=True)
    evaluate.add_argument("--output", required=True)
    evaluate.add_argument("--bootstrap", type=int, default=0, help="resamples by work_id")
    compare = commands.add_parser("compare")
    compare.add_argument("--queries", required=True, help="JSON array of ComparisonItem")
    compare.add_argument("--candidates", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--k", type=int, default=5)
    retrieval = commands.add_parser("recall-at-k")
    retrieval.add_argument("--relevance", required=True)
    retrieval.add_argument("--rankings", required=True)
    retrieval.add_argument("--k", type=int, default=5)
    agreement = commands.add_parser("agreement", help="two or more annotators: Cohen and Fleiss")
    agreement.add_argument("annotators", nargs="+")
    agreement.add_argument("--output", required=True)
    cp = commands.add_parser("import-chinese-poetry", help="JSON files of chinese-poetry")
    cp.add_argument("inputs", nargs="+")
    cp.add_argument("--output", required=True)
    cp.add_argument("--era", default="unknown")
    cp.add_argument("--genre", default="poetry")
    cp.add_argument("--revision", default="unknown", help="git commit of the source repository")
    texts = commands.add_parser("import-texts", help="folder of .txt poems + metadata CSV")
    texts.add_argument("folder")
    texts.add_argument("--metadata", required=True)
    texts.add_argument("--output", required=True)
    ift = commands.add_parser("build-ift", help="IFT dataset from one gold split")
    ift.add_argument("input")
    ift.add_argument("--output", required=True)
    ift.add_argument("--strategy", default="lexicon")
    ift.add_argument("--tasks", default="analysis,usage")
    tune = commands.add_parser("finetune", help="LoRA instruction tuning (needs .[finetune])")
    tune.add_argument("--train", required=True)
    tune.add_argument("--validation", required=True)
    tune.add_argument("--output", required=True)
    tune.add_argument("--base-model", required=True)
    tune.add_argument("--epochs", type=int, default=3)
    tune.add_argument("--batch-size", type=int, default=2)
    tune.add_argument("--gradient-accumulation", type=int, default=8)
    tune.add_argument("--learning-rate", type=float, default=2e-4)
    tune.add_argument("--lora-r", type=int, default=16)
    tune.add_argument("--max-length", type=int, default=4096)
    fert = commands.add_parser("fertility", help="tokenizer fertility on a corpus (H2)")
    fert.add_argument("corpus")
    fert.add_argument("--language", choices=["zh", "kk"], required=True)
    fert.add_argument("--tokenizers", nargs="+", required=True)
    fert.add_argument("--output", required=True)
    bpe = commands.add_parser("train-tokenizer", help="BPE tokenizer, default 50K vocabulary")
    bpe.add_argument("corpus")
    bpe.add_argument("--language", choices=["zh", "kk"], required=True)
    bpe.add_argument("--vocab-size", type=int, default=50000)
    bpe.add_argument("--output", required=True)
    probe = commands.add_parser("probe", help="layer-wise probing and MDL (H3)")
    probe.add_argument("gold")
    probe.add_argument("--model", required=True)
    probe.add_argument("--output", required=True)
    probe.add_argument("--max-length", type=int, default=512)
    experiment = commands.add_parser("experiment", help="run a methods x models comparison")
    experiment.add_argument("--config", required=True)
    experiment.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"Error: {exc}\n")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def make_pipeline(backend=None, strategy=None):
    from app.core.config import Settings
    from app.nlp.pipeline import build_pipeline

    settings = Settings(**({"nlp_backend": backend} if backend else {}))
    return build_pipeline(settings, strategy)


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
        records, report = clean_corpus(
            read_corpus(args.input),
            verse_lines=args.verse_lines,
            remove_editorial=not args.keep_editorial,
        )
        write_corpus(args.output, records)
        save_json(str(args.output) + ".duplicates.json", report)
    elif command == "split":
        for name, records in split_corpus(read_corpus(args.input)).items():
            write_corpus(Path(args.output) / f"{name}.jsonl", records)
    elif command == "label-studio-export":
        from app.nlp.annotation import export_tasks

        save_json(
            args.output,
            export_tasks(read_corpus(args.input), prefill_candidates=args.prefill_candidates),
        )
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
        result = make_pipeline(args.backend, args.strategy).analyze(text, args.language)
        save_json(args.output, result.model_dump())
    elif command == "predict":
        pipeline = make_pipeline(args.backend, args.strategy)
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
        gold = read_corpus(args.gold)
        report = evaluate(gold, predictions)
        if args.bootstrap:
            from app.nlp.evaluation import bootstrap

            report["bootstrap"] = bootstrap(gold, predictions, samples=args.bootstrap)
        save_json(args.output, report)
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

        save_json(args.output, annotation_agreement(*(read_corpus(p) for p in args.annotators)))
    elif command == "import-chinese-poetry":
        from app.nlp.importers import import_chinese_poetry

        write_corpus(
            args.output,
            import_chinese_poetry(
                args.inputs, era=args.era, genre=args.genre, revision=args.revision
            ),
        )
    elif command == "import-texts":
        from app.nlp.importers import import_text_folder

        write_corpus(args.output, import_text_folder(args.folder, args.metadata))
    elif command == "build-ift":
        from app.nlp.ift import build_ift, write_ift

        records = read_corpus(args.input)
        rows = build_ift(records, strategy=args.strategy, tasks=tuple(args.tasks.split(",")))
        print(write_ift(args.output, rows, records, args.strategy))
    elif command == "finetune":
        from app.nlp.finetune import finetune_lora

        meta = finetune_lora(
            args.train,
            args.validation,
            args.output,
            model_name=args.base_model,
            epochs=args.epochs,
            batch_size=args.batch_size,
            gradient_accumulation=args.gradient_accumulation,
            learning_rate=args.learning_rate,
            lora_r=args.lora_r,
            lora_alpha=2 * args.lora_r,
            max_length=args.max_length,
        )
        print(meta["model_version"], meta["best_validation_loss"])
    elif command == "fertility":
        from app.nlp.tokenization import compare_tokenizers

        texts = [r.text for r in read_corpus(args.corpus) if r.language == args.language]
        save_json(args.output, compare_tokenizers(args.tokenizers, texts, args.language))
    elif command == "train-tokenizer":
        from app.nlp.tokenization import train_bpe

        texts = [r.text for r in read_corpus(args.corpus) if r.language == args.language]
        print(train_bpe(texts, args.output, args.vocab_size))
    elif command == "probe":
        from app.nlp.probing import probe_layers

        save_json(
            args.output,
            probe_layers(args.model, read_corpus(args.gold), max_length=args.max_length),
        )
    elif command == "experiment":
        from app.nlp.experiment import run_experiment

        result = run_experiment(args.config, args.output)
        print(f"{len(result['runs'])} runs; summary: {args.output}/summary.md")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
