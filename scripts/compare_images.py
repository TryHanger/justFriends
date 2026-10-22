"""Cross-cultural comparison of figurative images in Chinese and Kazakh poetry (ТЗ goal).

Both sides were annotated by the same annotator (Claude) with the same taxonomy, so the
distributions are comparable:
* zh: 100 Shijing and Tang poems (annotation/zh_poetry_claude_labels.jsonl via
  data/processed/pilot/zh_claude_silver_100.jsonl) and Wang Yi's Chu Ci images;
* kk: 100 poems by Abai (data/processed/kk_ensemble/claude_silver_100.jsonl) and the
  figurative («ауыс.») senses of the Kazakh explanatory dictionary.

For source and target domains a chi-square test of independence (language x domain) and
adjusted standardized residuals show which domains are over- or under-represented in a
language (|residual| > 1.96 ≈ p < 0.05 per cell). Mappings source → target and the most
frequent image words are listed per language.

    python -m scripts.compare_images
"""

import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import chi2_contingency

from app.nlp.corpus import read_corpus

ZH = Path("data/processed/pilot/zh_claude_silver_100.jsonl")
KK = Path("data/processed/kk_ensemble/claude_silver_100.jsonl")
WANGYI = Path("data/processed/wangyi/chuci_wangyi.jsonl")
DICTIONARY = Path("data/processed/kk_usage/kk_usage_dictionary.jsonl")
OUTPUT = Path("data/processed/comparison/images_zh_kk.json")
SKIP = {"unknown", "other"}


def table(spans_by_language: dict, field: str) -> dict:
    """Counts, shares, chi-square and adjusted residuals for one field (source/target)."""
    languages = list(spans_by_language)
    counts = {
        lang: Counter(getattr(s, field) for s in spans) for lang, spans in spans_by_language.items()
    }
    domains = sorted({d for c in counts.values() for d in c} - SKIP)
    # Domains rare in both languages make the test unreliable; they are pooled into "rare".
    frequent = [d for d in domains if sum(counts[lang][d] for lang in languages) >= 5]
    rare = [d for d in domains if d not in frequent]
    rows = frequent + (["rare"] if rare else [])
    matrix = np.array(
        [
            [
                counts[lang][d] if d != "rare" else sum(counts[lang][r] for r in rare)
                for lang in languages
            ]
            for d in rows
        ],
        dtype=float,
    )
    chi2, p, dof, expected = chi2_contingency(matrix)
    n = matrix.sum()
    row_share, col_share = matrix.sum(1) / n, matrix.sum(0) / n
    residuals = (matrix - expected) / np.sqrt(
        expected * (1 - row_share[:, None]) * (1 - col_share[None, :])
    )
    total = matrix.sum(0)
    return {
        "test": {"chi2": float(chi2), "dof": int(dof), "p_value": float(p), "n": int(n)},
        "rare_pooled": rare,
        "domains": {
            d: {
                lang: {
                    "count": int(matrix[i, j]),
                    "share": float(matrix[i, j] / total[j]),
                    "adjusted_residual": float(residuals[i, j]),
                }
                for j, lang in enumerate(languages)
            }
            for i, d in enumerate(rows)
        },
    }


def mappings(spans, top: int = 12) -> list:
    pairs = Counter(
        (s.source_domain, s.target_domain)
        for s in spans
        if s.source_domain not in SKIP and s.target_domain not in SKIP
    )
    total = sum(pairs.values())
    return [
        {"source": a, "target": b, "count": c, "share": c / total}
        for (a, b), c in pairs.most_common(top)
    ]


def images(spans, top: int = 20) -> list:
    words = Counter((s.entity or s.text).lower() for s in spans)
    return [{"image": w, "count": c} for w, c in words.most_common(top)]


def main() -> None:
    zh, kk = read_corpus(ZH), read_corpus(KK)
    spans = {"zh": [s for r in zh for s in r.spans], "kk": [s for r in kk for s in r.spans]}
    lines = {
        "zh": sum(r.text.count("\n") + 1 for r in zh),
        "kk": sum(r.text.count("\n") + 1 for r in kk),
    }
    report = {
        "corpora": {
            "zh": {
                "poems": len(zh),
                "figures": len(spans["zh"]),
                "lines": lines["zh"],
                "eras": dict(Counter(r.era for r in zh)),
                "poems_with_figures": sum(bool(r.spans) for r in zh),
            },
            "kk": {
                "poems": len(kk),
                "figures": len(spans["kk"]),
                "lines": lines["kk"],
                "authors": dict(Counter(r.author for r in kk)),
                "poems_with_figures": sum(bool(r.spans) for r in kk),
            },
        },
        "figures_per_100_lines": {lang: 100 * len(spans[lang]) / lines[lang] for lang in spans},
        "labels": {lang: dict(Counter(s.label for s in spans[lang])) for lang in spans},
        "source_domain": table(spans, "source_domain"),
        "target_domain": table(spans, "target_domain"),
        "mappings": {lang: mappings(spans[lang]) for lang in spans},
        "images": {lang: images(spans[lang]) for lang in spans},
    }
    wangyi = [s for r in read_corpus(WANGYI) for s in r.spans]
    report["wangyi_chuci"] = {
        "images": len(wangyi),
        "pairs": Counter(f"{s.text} → {s.tenor}" for s in wangyi).most_common(41),
    }
    quotations = [json.loads(line) for line in DICTIONARY.read_text(encoding="utf-8").splitlines()]
    figurative = Counter(q["headword"] for q in quotations if q["usage_type"] == "metaphorical")
    senses = {}
    for q in quotations:
        if q["usage_type"] == "metaphorical" and q["definition"]:
            senses.setdefault(q["headword"], set()).add(q["definition"][:80])
    report["kk_dictionary_figurative_senses"] = [
        {"headword": w, "quotations": c, "senses": sorted(senses.get(w, []))[:3]}
        for w, c in figurative.most_common(25)
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for field in ("source_domain", "target_domain"):
        t = report[field]
        print(
            f"\n{field}: chi2={t['test']['chi2']:.1f} dof={t['test']['dof']} p={t['test']['p_value']:.2g}"
        )
        for d, v in t["domains"].items():
            print(
                f"  {d:12} zh {v['zh']['share']:5.0%} ({v['zh']['adjusted_residual']:+.1f})   kk {v['kk']['share']:5.0%} ({v['kk']['adjusted_residual']:+.1f})"
            )
    for lang in ("zh", "kk"):
        print(
            f"\n{lang} mappings:",
            [(m["source"], m["target"], m["count"]) for m in report["mappings"][lang][:8]],
        )
        print(f"{lang} images:", [(i["image"], i["count"]) for i in report["images"][lang][:15]])
    print(
        "\ndensity per 100 lines:",
        {k: round(v, 1) for k, v in report["figures_per_100_lines"].items()},
    )


if __name__ == "__main__":
    main()
