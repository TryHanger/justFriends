"""Comparison runner for ТЗ этапы 2-4: methods x models x languages on one gold test split.

Config (JSON):
{
  "name": "pilot",
  "gold": "data/gold/splits/test.jsonl",
  "bootstrap": 1000,
  "runs": [
    {"name": "baseline", "backend": "baseline"},
    {"name": "gpt-zero", "backend": "openai", "strategy": "zero_shot"},
    {"name": "claude-full", "backend": "anthropic", "model": "claude-opus-5-5",
     "strategy": "few_shot+cot+rag+lexicon"},
    {"name": "qwen-fewshot", "backend": "ollama", "model": "qwen2.5:7b-instruct",
     "strategy": "few_shot+lexicon"},
    {"name": "qwen-ift", "backend": "hf", "model": "Qwen/Qwen2.5-7B-Instruct",
     "adapter": "models/qwen-ift", "strategy": "lexicon"}
  ]
}
Each run writes predictions.json, failures.json, metrics.json; the summary table compares
F1 against ТЗ targets. Provider errors are kept as empty predictions *and* reported, so they
lower recall instead of silently shrinking the test set. Finished runs are not repeated.
"""

import csv
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

from app.nlp.corpus import manifest, read_corpus, save_json
from app.nlp.evaluation import TZ_TARGETS, bootstrap, evaluate
from app.schemas.analysis import AnalysisResult

MODEL_SETTING = {
    "openai": "openai_model",
    "anthropic": "anthropic_model",
    "ollama": "ollama_model",
    "hf": "hf_model",
    "xlmr": "xlmr_model_path",
    "hybrid": "xlmr_model_path",
}
SUMMARY_METRICS = (
    "metaphor_detection",
    "entity_extraction",
    "usage_classification",
    "semantic_labeling",
)


def run_settings(run: dict):
    from app.core.config import Settings

    overrides = {"nlp_backend": run["backend"]}
    if run.get("model"):
        overrides[MODEL_SETTING[run["backend"]]] = run["model"]
    if run.get("adapter"):
        overrides["hf_adapter"] = run["adapter"]
    for key in ("temperature", "top_p"):
        if key in run:
            overrides[f"llm_{key}"] = run[key]
    if run.get("hybrid_llm_backend"):
        overrides["hybrid_llm_backend"] = run["hybrid_llm_backend"]
    return Settings(**overrides)


def run_experiment(config_path: str | Path, output_dir: str | Path, pipeline_factory=None) -> dict:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    gold = read_corpus(config["gold"])
    names = [r["name"] for r in config["runs"]]
    if len(set(names)) != len(names):
        raise ValueError("Run names must be unique")
    output = Path(output_dir)
    summary = []
    for run in config["runs"]:
        folder = output / run["name"]
        metrics_path = folder / "metrics.json"
        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        else:
            metrics = _execute(run, gold, folder, config, pipeline_factory)
        summary.append(_summary_row(run, metrics))
    save_json(output / "summary.json", summary)
    _write_tables(output, summary)
    return {"runs": summary, "gold": manifest(gold)}


def _execute(run, gold, folder, config, pipeline_factory):
    from app.nlp.pipeline import build_pipeline

    if pipeline_factory:
        pipeline = pipeline_factory(run)
    else:
        pipeline = build_pipeline(run_settings(run), run.get("strategy"))
    predictions, failures = {}, {}
    for record in gold:
        try:
            predictions[record.id] = pipeline.analyze(record.text, record.language)
        except Exception as exc:  # recorded per document; the run continues
            failures[record.id] = f"{type(exc).__name__}: {str(exc)[:300]}"
            predictions[record.id] = AnalysisResult(
                language=record.language,
                model_version=f"failed:{run['name']}",
                metaphors=[],
                warnings=["Provider or parsing failure; empty prediction counted in metrics."],
            )
    save_json(folder / "predictions.json", {k: v.model_dump() for k, v in predictions.items()})
    save_json(folder / "failures.json", failures)
    metrics = evaluate(gold, predictions)
    if config.get("bootstrap"):
        metrics["bootstrap"] = bootstrap(gold, predictions, samples=int(config["bootstrap"]))
    methods = {json.dumps(p.method, sort_keys=True) for p in predictions.values() if p.method}
    metrics["run"] = {
        **run,
        "failures": len(failures),
        "documents": len(gold),
        "gold_sha256": manifest(gold)["sha256"],
        "method_records": [json.loads(m) for m in sorted(methods)][:5],
        "finished_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
    }
    save_json(folder / "metrics.json", metrics)
    return metrics


def _summary_row(run: dict, metrics: dict) -> dict:
    row = {
        "run": run["name"],
        "backend": run["backend"],
        "model": run.get("model") or "",
        "strategy": run.get("strategy") or "",
        "failures": metrics.get("run", {}).get("failures"),
    }
    for language in ("all", "zh", "kk"):
        for name in SUMMARY_METRICS:
            value = (metrics.get(language) or {}).get(name)
            row[f"{language}.{name}.f1"] = None if value is None else round(value["f1"], 4)
    for name, target in metrics.get("tz_targets", {}).items():
        if name != "inter_annotator_kappa":
            row[f"tz.{name}.met"] = target["met"]
    return row


def _write_tables(output: Path, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with (output / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    headers = ["run", "strategy", "failures"] + [f"all.{m}.f1" for m in SUMMARY_METRICS]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append(
            "| " + " | ".join("" if row.get(h) is None else str(row.get(h)) for h in headers) + " |"
        )
    targets = ", ".join(f"{k} ≥ {v}" for k, v in TZ_TARGETS.items() if k != "inter_annotator_kappa")
    lines += [
        "",
        f"Целевые значения ТЗ (F1): {targets}. Пустая ячейка: в gold нет разметки для метрики.",
    ]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
