import json

import pytest

from app.nlp.annotation import export_tasks, import_tasks, python_offset
from app.nlp.contracts import ModelSpan, resolve_language, validate_result
from app.nlp.corpus import Poem, assert_disjoint, clean_corpus, require_gold, split_corpus
from app.nlp.evaluation import annotation_agreement, evaluate, recall_at_k
from app.nlp.baseline import LexicalDetector
from app.nlp.llm import parse_output
from app.schemas.analysis import AnalysisResult


def poem(text="心海", **updates):
    data = dict(
        id="p1",
        work_id="w1",
        language="zh",
        text=text,
        title="test",
        author="test",
        source_url="synthetic://test",
        license="test",
        license_verified=True,
        synthetic=True,
        annotation_status="gold",
        annotators=["a"],
        adjudicator="b",
    )
    data.update(updates)
    return Poem(**data)


def span(text="心海", start=0, **updates):
    return ModelSpan(
        **{
            **dict(
                text=text,
                start=start,
                end=start + len(text),
                label="metaphor",
                source_domain="water",
                target_domain="emotion",
                confidence=0.5,
                rationale="test",
            ),
            **updates,
        }
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"end": 0},
        {"start": True},
        {"end": 1.5},
        {"confidence": float("nan")},
        {"label": "invented"},
        {"source_domain": "invented"},
    ],
)
def test_invalid_span(updates):
    with pytest.raises(ValueError):
        span(**updates)


def test_exact_unicode_and_crlf_offsets():
    text = "🌙\r\n心海"
    result = LexicalDetector().analyze(text, "zh")
    assert (result.metaphors[0].start, result.metaphors[0].end) == (3, 5)
    validate_result(text, "zh", result)
    result.metaphors[0].end = 100
    with pytest.raises(ValueError):
        validate_result(text, "zh", result)
    assert python_offset(text, 4, "utf16") == 3
    with pytest.raises(ValueError):
        python_offset(text, 1, "utf16")


def test_language_and_overlap():
    assert resolve_language("心海", "auto") == "zh"
    assert resolve_language("Өмір", "auto") == "kk"
    with pytest.raises(ValueError):
        resolve_language("hello", "auto")
    with pytest.raises(ValueError):
        poem(spans=[span(), span()])
    with pytest.raises(ValueError):
        validate_result("心海", "kk", LexicalDetector().analyze("心海", "zh"))


def test_clean_annotated_offsets_and_duplicate_conflicts():
    original = poem("\ufeff\r\n心海 ", spans=[span(start=3)])
    cleaned, _ = clean_corpus([original])
    assert cleaned[0] == original
    with pytest.raises(ValueError, match="Annotated duplicate"):
        clean_corpus([poem(), poem(id="p2")])
    first = poem("心海 \r\n", annotation_status="unlabeled", spans=[])
    clean, duplicates = clean_corpus([first, poem(id="p2", annotation_status="unlabeled")])
    assert len(clean) == 1 and duplicates[0]["removed"] == "p2"


def test_split_leakage_and_synthetic_guard():
    records = [poem(text=f"poem{i}", id=str(i), work_id=str(i // 2)) for i in range(12)]
    split = split_corpus(records)
    assert sum(map(len, split.values())) == len(records)
    assert split == split_corpus(records)
    assert_disjoint(*split.values())
    with pytest.raises(ValueError, match="leakage"):
        assert_disjoint([records[0]], [records[1]])
    with pytest.raises(ValueError, match="Synthetic"):
        require_gold(records)


def test_metrics_include_false_positives_and_missing_ids():
    records = [poem(spans=[span()]), poem("他写下心海。", id="p2", work_id="w2")]
    preds = {r.id: LexicalDetector().analyze(r.text, "zh") for r in records}
    metrics = evaluate(records, preds)
    assert metrics["all"]["metaphor_detection"]["precision"] == 0.5
    assert metrics["all"]["metaphor_detection"]["recall"] == 1
    assert metrics["kk"]["documents"] == 0
    with pytest.raises(ValueError):
        evaluate(records, {"p1": preds["p1"]})
    assert recall_at_k({"q": ["a", "b"]}, {"q": ["a", "c"]}, 1) == 0.5
    assert annotation_agreement([records[0]], [records[0]])["character_kappa"] is None


def test_llm_invalid_output_and_model_version_owned_by_code():
    payload = {"language": "zh", "metaphors": [span().model_dump()]}
    result = parse_output(json.dumps(payload), "心海", "zh", "test-version")
    assert result.model_version == "test-version" and result.needs_review
    payload["metaphors"][0]["end"] = 200
    with pytest.raises(ValueError):
        parse_output(json.dumps(payload), "心海", "zh", "test-version")
    payload["metaphors"] = []
    with pytest.raises(ValueError):
        parse_output(json.dumps(payload), "心海", "kk", "test-version")
    payload["model_version"] = "spoofed"
    with pytest.raises(ValueError):
        parse_output(json.dumps(payload), "心海", "zh", "test-version")


def test_label_studio_never_uses_predictions_as_gold():
    tasks = export_tasks([poem("🌙心海", annotation_status="unlabeled")])
    tasks[0]["predictions"] = [{"result": []}]
    with pytest.raises(ValueError):
        import_tasks(tasks)
    tasks[0]["annotations"] = [
        {
            "completed_by": 7,
            "result": [
                {
                    "id": "s",
                    "type": "labels",
                    "from_name": "figure",
                    "value": {"start": 2, "end": 4, "text": "心海", "labels": ["metaphor"]},
                },
                {
                    "id": "s",
                    "type": "choices",
                    "from_name": "source_domain",
                    "value": {"choices": ["water"]},
                },
                {
                    "id": "s",
                    "type": "choices",
                    "from_name": "target_domain",
                    "value": {"choices": ["emotion"]},
                },
            ],
        }
    ]
    record = import_tasks(tasks)[0]
    assert record.spans[0].start == 1 and record.annotation_status == "draft"
    assert import_tasks(tasks, adjudicator="Arslan")[0].annotation_status == "gold"
    tasks[0]["annotations"].append(tasks[0]["annotations"][0])
    with pytest.raises(ValueError):
        import_tasks(tasks)


def test_old_result_remains_readable():
    result = AnalysisResult(language="zh", model_version="old", metaphors=[])
    assert result.needs_review
