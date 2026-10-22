"""Tenor/ground fields, diagnostic quality metrics and token accounting."""

import json
from types import SimpleNamespace

import pytest

from app.nlp.evaluation import evaluate
from app.nlp.llm import OpenAIDetector, locate_tenor, parse_output
from app.nlp.quality import chrf
from app.schemas.analysis import AnalysisResult
from tests.test_nlp_contracts import llm_item, llm_payload, poem, span


def test_tenor_is_located_nearest_to_the_image_or_left_implicit():
    text = "火在烧。火是痛苦的赠礼"
    assert locate_tenor(text, "火", 6, 11) == (4, 5)
    assert locate_tenor(text, "水", 6, 11) is None
    result = parse_output(
        json.dumps(
            llm_payload(llm_item(text="痛苦的赠礼", entity="赠礼", tenor="火", ground="折磨"))
        ),
        text,
        "zh",
        "t",
    )
    item = result.metaphors[0]
    assert (item.tenor, item.tenor_start, item.tenor_end, item.ground) == ("火", 4, 5, "折磨")
    implicit = parse_output(
        json.dumps(llm_payload(llm_item(tenor="", ground="深"))), "心海", "zh", "t"
    ).metaphors[0]
    assert implicit.tenor is None and implicit.tenor_start is None


def test_tenor_offsets_must_match_text():
    with pytest.raises(ValueError):
        span(tenor="火", tenor_start=0)
    with pytest.raises(ValueError):
        poem("心海", spans=[span(tenor="火", tenor_start=0, tenor_end=1)])


def test_chrf_rewards_partial_character_overlap():
    assert chrf("折磨的感觉", "折磨的感觉") == pytest.approx(1.0)
    assert 0 < chrf("痛苦的感觉", "折磨的感觉") < 1
    assert chrf("", "折磨") == 0.0


def test_overlap_document_calibration_and_unknown_domains():
    gold = [
        poem(
            "我的心海很深",
            spans=[
                span(
                    start=2,
                    tenor="我",
                    tenor_start=0,
                    tenor_end=1,
                    ground="深",
                    source_domain="unknown",
                    target_domain="unknown",
                )
            ],
        ),
        poem("今天下雨", id="neg", work_id="w-neg"),
    ]
    predictions = {
        # Boundary differs by one character: exact miss, overlap hit.
        gold[0].id: AnalysisResult(
            language="zh",
            model_version="t",
            metaphors=[
                span(
                    text="心海很",
                    start=2,
                    confidence=0.9,
                    tenor="我",
                    tenor_start=0,
                    tenor_end=1,
                    ground="很深",
                    source_domain="unknown",
                    target_domain="unknown",
                )
            ],
        ),
        # False alarm on a text without metaphors.
        "neg": AnalysisResult(
            language="zh", model_version="t", metaphors=[span(text="下雨", start=2, confidence=0.2)]
        ),
    }
    report = evaluate(gold, predictions)
    section = report["all"]
    assert section["metaphor_detection"]["tp"] == 0
    assert section["overlap_detection"]["tp"] == 1 and section["overlap_detection"]["fp"] == 1
    assert section["document_detection"]["false_positive_rate"] == 1.0
    assert section["tenor_localization"]["f1"] == 1.0
    assert section["text_fields"]["ground"]["exact_match"] == 0.0
    assert 0 < section["text_fields"]["ground"]["chrf"] < 1
    # unknown == unknown is not counted as a correct semantic label.
    assert section["semantic_labeling"] is None
    calibration = section["calibration"]
    assert calibration["predicted_spans"] == 2 and 0 <= calibration["ece"] <= 1
    assert calibration["by_threshold"][-1]["precision"] == 1.0
    assert report["by_genre"]["zh:poetry"]["overlap_f1"] == pytest.approx(2 / 3)
    assert report["reliability"]["documents"] == 2


def test_openai_usage_is_recorded_in_method():
    def create(**kwargs):
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(llm_payload(llm_item())),
            usage=SimpleNamespace(input_tokens=1200, output_tokens=80),
        )

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = OpenAIDetector("m", "k", client, strategy="zero_shot").analyze("心海", "zh")
    assert result.method["usage"] == {"requests": 1, "input_tokens": 1200, "output_tokens": 80}
    report = evaluate([poem(spans=[span()])], {"p1": result})
    assert report["reliability"]["mean_input_tokens"] == 1200


def test_failed_russian_translation_keeps_analysis_with_warning():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if "translations" in json.dumps(kwargs["text"]["format"]["schema"]):
            return SimpleNamespace(
                status="completed", output_text=json.dumps({"translations": ["not russian"]})
            )
        item = llm_item(rationale="English rationale")
        return SimpleNamespace(status="completed", output_text=json.dumps(llm_payload(item)))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = OpenAIDetector("m", "k", client, strategy="zero_shot").analyze("心海", "zh")
    assert len(calls) == 3  # analysis, translation, one retry of the rejected translation
    assert result.metaphors[0].rationale == "English rationale"
    assert any("could not be translated" in w for w in result.warnings)


def test_kazakh_explanation_is_not_taken_for_russian():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            translated = "Сердце уподоблено морю: образ «теңіз» передаёт безбрежность чувств."
            return SimpleNamespace(
                status="completed", output_text=json.dumps({"translations": [translated]})
            )
        item = llm_item(rationale="Жүрек теңізге теңелген, бұл шексіз сезімдерді білдіреді.")
        return SimpleNamespace(status="completed", output_text=json.dumps(llm_payload(item)))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = OpenAIDetector("m", "k", client, strategy="zero_shot").analyze("心海", "zh")
    assert len(calls) == 2  # Kazakh Cyrillic triggered the Russian pass
    assert result.metaphors[0].rationale.startswith("Сердце уподоблено морю")
    assert not any("could not be translated" in w for w in result.warnings)


def test_chinese_explanation_with_russian_mip_labels_is_translated():
    from app.nlp.llm import _russian

    chinese = "国家被比作船，暗示其在人民的支持下才能航行。 (MIP — базовое: 国 — 国家; контраст: 不同领域)"
    russian = (
        "Государство уподоблено лодке: «国如舟» держится на народе. (MIP — базовое: 国 — страна)"
    )
    assert not _russian(chinese)  # our own Cyrillic labels must not make it "Russian"
    assert _russian(russian)  # quoted and short source words inside Russian prose are fine


def test_review_report_flags_unchanged_suggestions():
    from app.nlp.annotation import review_report

    def region(rid, origin):
        return {
            "id": rid,
            "type": "labels",
            "from_name": "figure",
            "origin": origin,
            "value": {"start": 0, "end": 1, "text": "x", "labels": ["metaphor"]},
        }

    suggestion = {"result": [region("a", None), region("b", None)]}
    tasks = [
        {
            "data": {"id": "t1"},
            "predictions": [1],
            "annotations": [
                {
                    "result": [region("a", "prediction"), region("b", "prediction")],
                    "prediction": suggestion,
                    "lead_time": 4.0,
                }
            ],
        },
        {
            "data": {"id": "t2"},
            "predictions": [2],
            "annotations": [
                {
                    "result": [region("a", "prediction-changed"), region("c", "manual")],
                    "prediction": suggestion,
                    "lead_time": 300.0,
                }
            ],
        },
    ]
    summary = review_report(tasks)["summary"]
    assert (summary["accepted"], summary["edited"], summary["added"], summary["deleted"]) == (
        2,
        1,
        1,
        1,
    )
    assert summary["tasks_accepted_without_changes"] == 1 and summary["warning"] is None


def test_calibrator_rescales_confidence_and_flags_low_figures():
    from app.nlp.calibration import UNCALIBRATED, Calibrator, platt
    from app.schemas.analysis import AnalysisResult

    def figure(start, confidence):
        return {
            "text": "心海"[start],
            "start": start,
            "end": start + 1,
            "label": "metaphor",
            "source_domain": "water",
            "target_domain": "emotion",
            "confidence": confidence,
            "rationale": "Образ.",
        }

    result = AnalysisResult(
        language="zh",
        model_version="openai:m",
        warnings=[UNCALIBRATED],
        metaphors=[figure(0, 0.95), figure(1, 0.6)],
    )
    fit = {"a": 1.0, "b": -1.5, "source": "CMDAG", "spans": 120, "ece_after": 0.05}
    calibrated = Calibrator({"openai:m": {"zh": fit}}, threshold=0.7).apply(result)
    assert calibrated.metaphors[0].confidence == round(platt(0.95, 1.0, -1.5), 3)
    assert calibrated.metaphors[0].confidence < 0.95  # an overconfident model is pulled down
    assert UNCALIBRATED not in calibrated.warnings
    # 0.95 -> 0.81 stays above the 0.7 threshold, 0.6 -> 0.35 falls below it.
    assert any(w.startswith("1 of 2 figure(s) below") for w in calibrated.warnings)
    assert calibrated.needs_review and calibrated.method["calibration"]["spans"] == 120
    # Unknown model or language: untouched.
    assert Calibrator({}, threshold=0.7).apply(result) == result


def test_candidate_reasoning_is_translated_too():
    def create(**kwargs):
        if "translations" in json.dumps(kwargs["text"]["format"]["schema"]):
            items = json.loads(kwargs["input"])["items"]
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"translations": ["Перевод на русский."] * len(items)}),
            )
        literal = {
            "text": "山",
            "start": 2,
            "end": 3,
            "entity_type": "body",
            "reasoning": "Жүрек — орган, нақты мағынада қолданылған.",
        }
        item = llm_item(rationale="Образ моря передаёт чувства.")
        payload = llm_payload(item, literal=[literal])
        return SimpleNamespace(status="completed", output_text=json.dumps(payload))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = OpenAIDetector("m", "k", client, strategy="zero_shot").analyze("心海山", "zh")
    literal = next(c for c in result.candidates if c.usage_type == "literal")
    assert literal.reasoning == "Перевод на русский."
    assert result.metaphors[0].rationale == "Образ моря передаёт чувства."  # already Russian


def test_wrong_number_of_translations_keeps_the_analysis():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if "translations" in json.dumps(kwargs["text"]["format"]["schema"]):
            return SimpleNamespace(
                status="completed", output_text=json.dumps({"translations": ["Один.", "Два."]})
            )
        item = llm_item(rationale="English rationale")
        return SimpleNamespace(status="completed", output_text=json.dumps(llm_payload(item)))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = OpenAIDetector("m", "k", client, strategy="zero_shot").analyze("心海", "zh")
    assert len(calls) == 3  # analysis, translation, retry
    assert result.metaphors[0].rationale == "English rationale"
    assert any("could not be translated" in w for w in result.warnings)
