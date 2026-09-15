"""Synthetic fixtures only: these are not authentic poems or a research gold corpus."""

from pathlib import Path

from app.nlp.baseline import LexicalDetector
from app.nlp.corpus import Poem, save_json, write_corpus
from app.nlp.contracts import ModelSpan

ROOT = Path(__file__).resolve().parents[1]


def main():
    examples = [
        ("zh", "我的心海泛起波浪。", "心海", "metaphor", "water", "emotion"),
        ("zh", "黑夜里，心火仍在燃烧。", "心火", "metaphor", "fire", "emotion"),
        ("zh", "时间是一条河，静静流过。", "时间是一条河", "metaphor", "water", "time"),
        ("zh", "窗外有一棵树。", None, None, None, None),
        ("zh", "他写下“心海”两个字。", None, None, None, None),
        ("zh", "风在耳边低语。", "低语", "personification", "person", "nature"),
        ("kk", "Өмір өзені тоқтамай ағады.", "Өмір өзені", "metaphor", "water", "life"),
        ("kk", "Жүрек оты сөнбейді.", "Жүрек оты", "metaphor", "fire", "emotion"),
        ("kk", "Түнде үміт сәулесі көрінді.", "үміт сәулесі", "metaphor", "light", "mind"),
        ("kk", "Аулада бір ағаш өсіп тұр.", None, None, None, None),
        ("kk", "Тақтада «өмір өзені» деп жазылған.", None, None, None, None),
        ("kk", "Жел сыбырлады.", "сыбырлады", "personification", "person", "nature"),
    ]
    records = []
    for i, (language, text, phrase, label, source, target) in enumerate(examples, 1):
        spans = []
        if phrase:
            start = text.index(phrase)
            spans.append(
                ModelSpan(
                    text=phrase,
                    start=start,
                    end=start + len(phrase),
                    label=label,
                    source_domain=source,
                    target_domain=target,
                    confidence=1.0,
                    rationale="Synthetic software-test annotation, not human gold.",
                )
            )
        records.append(
            Poem(
                id=f"synthetic-{i}",
                work_id=f"synthetic-{i}",
                language=language,
                text=text,
                title=f"Synthetic fixture {i}",
                author="Synthetic fixture",
                source_url="synthetic://justfriends/nlp-tests",
                license="synthetic-test",
                license_verified=True,
                synthetic=True,
                annotation_status="gold",
                annotators=["synthetic-fixture"],
                adjudicator="synthetic-fixture",
                spans=spans,
            )
        )
    write_corpus(ROOT / "data/examples/synthetic.jsonl", records)
    for record in (records[0], records[6]):
        result = LexicalDetector().analyze(record.text, record.language)
        save_json(
            ROOT / f"contracts/examples/analyze-{record.language}.request.json",
            {"text": record.text, "language": record.language},
        )
        save_json(
            ROOT / f"contracts/examples/analyze-{record.language}.response.json",
            {"analysis_id": 1, "status": "queued", "status_url": "/api/v1/analyses/1"},
        )
        save_json(
            ROOT / f"contracts/examples/analyze-{record.language}.completed.json",
            {
                "analysis_id": 1,
                "status": "completed",
                "source_name": None,
                "created_at": "2026-09-15T00:00:00+00:00",
                "result": result.model_dump(),
                "error": None,
            },
        )
    save_json(
        ROOT / "contracts/examples/compare-queries.json",
        [{"id": "zh-1", "text": "时间是一条河", "language": "zh", "context": ""}],
    )
    save_json(
        ROOT / "contracts/examples/compare-candidates.json",
        [
            {"id": "kk-1", "text": "өмір өзені", "language": "kk", "context": ""},
            {"id": "kk-2", "text": "жүрек оты", "language": "kk", "context": ""},
        ],
    )


if __name__ == "__main__":
    main()
