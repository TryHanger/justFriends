"""Features added for the technical specification (ТЗ): modules B-E, metrics, H1-H3 tooling."""

import json

import pytest

from app.nlp.annotation import export_tasks, import_tasks
from app.nlp.baseline import LexicalDetector
from app.nlp.evaluation import annotation_agreement, bootstrap, evaluate, fleiss_kappa
from app.nlp.lexicon import Lexicon, merge_candidates
from app.schemas.analysis import AnalysisResult, EntityCandidate
from tests.test_nlp_contracts import poem, span


def candidate(text, start, usage="metaphorical", entity_type="natural_phenomenon", origin="human"):
    return EntityCandidate(
        text=text,
        start=start,
        end=start + len(text),
        entity_type=entity_type,
        usage_type=usage,
        origin=origin,
    )


def test_kazakh_lexicon_keeps_affixes_alternation_and_avoids_homonyms():
    lexicon = Lexicon.load("kk")
    found = {c.text for c in lexicon.extract("Жүрегімде бөрілер, айдай сұлу. Ол айтты.")}
    assert {"Жүрегімде", "бөрілер", "айдай"} <= found
    assert "айтты" not in found and "Ол" not in found
    with pytest.raises(ValueError, match="forms"):
        Lexicon("kk", [{"term": "ай", "entity_type": "celestial", "meanings": []}])


def test_chinese_lexicon_longest_match_and_variants():
    found = [(c.text, c.start) for c in Lexicon.load("zh").extract("明月照蘭，月下狐。")]
    assert found == [("明月", 0), ("蘭", 3), ("月", 5), ("狐", 7)]


def test_merge_prefers_model_decisions():
    lexicon = [candidate("月", 1, usage=None, origin="lexicon")]
    model = [candidate("月", 1, usage="literal", origin="model"), candidate("海", 3)]
    merged = merge_candidates(model, lexicon)
    assert [(c.text, c.usage_type, c.origin) for c in merged] == [
        ("月", "literal", "lexicon+model"),
        ("海", "metaphorical", "human"),
    ]


def test_tz_metrics_entity_usage_semantic_and_targets():
    gold_span = span(
        entity="海",
        entity_type="natural_phenomenon",
        semantic_label="Глубина  чувств",
        sentiment="neutral",
    )
    gold = [
        poem(
            "心海明月",
            spans=[gold_span],
            candidates=[candidate("海", 1), candidate("明月", 2, "literal", "celestial")],
        ),
        poem(
            "明月", id="p2", work_id="w2", candidates=[candidate("明月", 0, "literal", "celestial")]
        ),
    ]
    good = span(entity="海", semantic_label="глубина чувств", sentiment="negative")
    predictions = {
        "p1": AnalysisResult(
            language="zh",
            model_version="t",
            metaphors=[good],
            candidates=[candidate("海", 1), candidate("明月", 2, "metaphorical")],
        ),
        "p2": AnalysisResult(language="zh", model_version="t", metaphors=[]),
    }
    report = evaluate(gold, predictions)["all"]
    assert report["entity_extraction"]["recall"] == pytest.approx(2 / 3)
    usage = report["usage_classification"]
    assert (usage["tp"], usage["fp"], usage["fn"]) == (1, 1, 0)
    # Semantic label matches after normalisation; sentiment does not.
    assert report["semantic_by_field"]["semantic_label"]["f1"] == 1.0
    assert report["semantic_by_field"]["sentiment"]["f1"] == 0.0
    assert report["semantic_labeling"]["tp"] == 3 and report["semantic_labeling"]["fp"] == 1
    targets = evaluate(gold, predictions)["tz_targets"]
    assert (
        targets["entity_extraction"]["met"] is False
        and targets["entity_extraction"]["target"] == 0.9
    )
    intervals = bootstrap(gold, predictions, samples=50)
    assert intervals["works"] == 2 and "usage_classification" in intervals["metrics"]


def test_fleiss_and_multi_annotator_agreement():
    assert fleiss_kappa([["a", "a"], ["a", "b"], ["b", "b"]]) == pytest.approx(1 / 3)
    assert fleiss_kappa([["a", "a", "a"], ["b", "b", "b"]]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        fleiss_kappa([["a", "a"], ["a"]])
    base = dict(spans=[span()], candidates=[candidate("海", 1)])
    a, b = poem("心海明月", **base), poem("心海明月", **base)
    c = poem("心海明月", spans=[], candidates=[candidate("海", 1, "literal")])
    report = annotation_agreement([a], [b], [c])
    assert report["annotators"] == 3 and len(report["pairs"]) == 3
    assert report["shared_candidates"] == 1 and report["character_fleiss_kappa"] is not None


def test_label_studio_entities_sentiment_and_semantic_label():
    tasks = export_tasks([poem("君子如兰", annotation_status="unlabeled")], prefill_candidates=True)
    assert tasks[0]["predictions"][0]["result"][0]["value"]["text"] == "兰"

    def choice(region, name, value):
        return {"id": region, "type": "choices", "from_name": name, "value": {"choices": [value]}}

    tasks[0]["annotations"] = [
        {
            "completed_by": 3,
            "result": [
                {
                    "id": "f",
                    "type": "labels",
                    "from_name": "figure",
                    "value": {"start": 0, "end": 4, "text": "君子如兰", "labels": ["simile"]},
                },
                choice("f", "source_domain", "plant"),
                choice("f", "target_domain", "person"),
                choice("f", "sentiment", "positive"),
                {
                    "id": "f",
                    "type": "textarea",
                    "from_name": "semantic_label",
                    "value": {"text": ["благородный муж"]},
                },
                {
                    "id": "e",
                    "type": "labels",
                    "from_name": "entity",
                    "value": {"start": 3, "end": 4, "text": "兰", "labels": ["entity"]},
                },
                choice("e", "entity_type", "plant"),
                choice("e", "usage_type", "metaphorical"),
            ],
        }
    ]
    record = import_tasks(tasks, adjudicator="Arslan")[0]
    figure = record.spans[0]
    assert (figure.entity, figure.entity_type, figure.semantic_label, figure.sentiment) == (
        "兰",
        "plant",
        "благородный муж",
        "positive",
    )
    assert record.candidates[0].usage_type == "metaphorical" and record.annotation_status == "gold"


def test_ift_dataset_uses_inference_prompt_and_valid_targets(tmp_path):
    from app.nlp.ift import build_ift, read_ift, write_ift

    records = [
        poem(
            "心海明月",
            spans=[span(entity="海", semantic_label="чувства")],
            candidates=[candidate("海", 1), candidate("明月", 2, "literal", "celestial")],
        )
    ]
    with pytest.raises(ValueError, match="Synthetic"):
        build_ift(records)
    rows = build_ift(records, allow_synthetic=True)
    assert [r["task"] for r in rows] == ["analysis", "usage", "usage"]
    answer = json.loads(rows[0]["messages"][-1]["content"])
    assert answer["literal_candidates"][0]["text"] == "明月"
    assert json.loads(rows[0]["messages"][1]["content"])["candidates"]
    card = write_ift(tmp_path / "ift.jsonl", rows, records, "lexicon")
    assert card["by_task"]["usage"] == 2 and len(read_ift(tmp_path / "ift.jsonl")) == 3
    with pytest.raises(ValueError, match="cot"):
        build_ift(records, strategy="cot", allow_synthetic=True)


def test_fertility_counts_word_forms_and_han_characters():
    from app.nlp.tokenization import fertility

    class CharTokenizer:
        unk_token_id = None
        vocab_size = 10

        def __call__(self, text, add_special_tokens=False):
            return {"input_ids": list(range(len(text.replace(" ", ""))))}

    kk = fertility(CharTokenizer(), ["Өмір өзені"], "kk")
    assert kk["words"] == 2 and kk["fertility"] == pytest.approx(4.5)
    zh = fertility(CharTokenizer(), ["明月，光。"], "zh")
    assert zh["words"] == 3 and zh["fertility"] == 1.0


def test_train_bpe_tokenizer(tmp_path):
    pytest.importorskip("transformers")
    from app.nlp.tokenization import train_bpe

    info = train_bpe(
        ["Өмір өзені ағады", "Жүрек оты сөнбейді"] * 20, tmp_path / "bpe", vocab_size=120
    )
    assert (tmp_path / "bpe" / "tokenizer.json").exists() and info["vocab_size"] <= 120


def test_probing_mdl_on_separable_features():
    pytest.importorskip("sklearn")
    from app.nlp.probing import grouped_f1, online_codelength

    features = [[float(i % 2), 0.1 * i] for i in range(40)]
    labels = [i % 2 for i in range(40)]
    groups = [str(i // 4) for i in range(40)]
    assert grouped_f1(features, labels, groups) == pytest.approx(1.0)
    noisy = online_codelength([[0.0] for _ in labels], labels)
    clean = online_codelength(features, labels)
    assert clean["compression"] > noisy["compression"]


def test_preprocessing_editorial_marks_variants_and_kazakh_lookalikes():
    from app.nlp.preprocess import normalize_kk, normalize_zh

    assert (
        normalize_zh("牀前明月光（注一），疑是地上霜①。", verse_lines=True)
        == "床前明月光，\n疑是地上霜。"
    )
    assert normalize_kk("Бiр ағаш, iPhone") == "Бір ағаш, iPhone"


def test_chinese_poetry_importer(tmp_path):
    from app.nlp.importers import import_chinese_poetry

    path = tmp_path / "chuci.json"
    path.write_text(
        json.dumps(
            [
                {
                    "title": "离骚",
                    "section": "离骚",
                    "author": "屈原",
                    "content": ["帝高阳之苗裔兮，", "朕皇考曰伯庸。"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record = import_chinese_poetry([path], era="Warring States", genre="chuci")[0]
    assert record.text.startswith("帝高阳") and not record.license_verified
    assert record.annotation_status == "unlabeled" and record.genre == "chuci"


def test_experiment_runner_records_failures(tmp_path):
    from app.nlp.corpus import write_corpus
    from app.nlp.experiment import run_experiment
    from app.nlp.pipeline import MetaphorPipeline

    gold = [poem(spans=[span()]), poem("明月", id="p2", work_id="w2")]
    write_corpus(tmp_path / "gold.jsonl", gold)
    config = {
        "gold": str(tmp_path / "gold.jsonl"),
        "bootstrap": 20,
        "runs": [
            {"name": "baseline", "backend": "baseline"},
            {"name": "broken", "backend": "baseline"},
        ],
    }
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

    class Broken:
        def analyze(self, text, language):
            raise ValueError("provider down")

    def factory(run):
        return MetaphorPipeline(Broken() if run["name"] == "broken" else LexicalDetector())

    result = run_experiment(tmp_path / "config.json", tmp_path / "out", factory)
    rows = {r["run"]: r for r in result["runs"]}
    assert rows["baseline"]["all.metaphor_detection.f1"] == 1.0
    assert rows["broken"]["failures"] == 2 and rows["broken"]["all.metaphor_detection.f1"] == 0.0
    assert (tmp_path / "out" / "summary.md").read_text(encoding="utf-8").startswith("| run")


def test_tz_export_rows_include_literal_candidates():
    from app.services.export import TZ_COLUMNS, tz_rows

    result = AnalysisResult(
        language="zh",
        model_version="t",
        metaphors=[span(entity="海", entity_type="natural_phenomenon", semantic_label="чувства")],
        candidates=[candidate("海", 1), candidate("明月", 3, "literal", "celestial")],
    )
    rows = tz_rows(result, "心海。明月")
    assert [r["Usage_Type"] for r in rows] == ["metaphorical", "literal"]
    assert rows[0]["Entity"] == "海" and rows[1]["Context_Sentence"] == "明月"
    assert set(TZ_COLUMNS) <= set(rows[0])


def test_baseline_classifies_candidates_and_pipeline_fills_context():
    from app.nlp.lexicon import CandidateExtractor
    from app.nlp.pipeline import MetaphorPipeline

    result = MetaphorPipeline(LexicalDetector(), extractor=CandidateExtractor()).analyze(
        "明月下，我的心海。", "zh"
    )
    # Commas split verse halves but not sentences: the whole sentence is the context.
    assert result.metaphors[0].context_sentence == "明月下，我的心海。"
    usage = {c.text: c.usage_type for c in result.candidates}
    assert usage == {"明月": "literal", "心": "metaphorical"}
