import json
from types import SimpleNamespace

import pytest

from app.nlp.llm import OpenAIDetector
from app.nlp.quality import reliability
from app.nlp.usage import BATCH_SCHEMA, INSTRUCTIONS, SCHEMA, UsageJudge, direct_question
from tests.test_nlp_contracts import llm_item, llm_payload

TEXT = "Тау басында бөрі ұлыды, жүрегі тас болды"  # бөрі 12..16, жүрегі тас 24..34, тас 31..34
FIGURE = llm_item("жүрегі тас", 24, entity="тас")
WOLF = {
    "text": "бөрі",
    "start": 12,
    "end": 16,
    "entity_type": "animal",
    "reasoning": "Волк в прямом значении.",
}


def fake_client(analysis, judge, calls, translate=None):
    """One client for both detectors: the request's schema tells which call it is."""

    def create(**kwargs):
        calls.append(kwargs)
        properties = kwargs["text"]["format"]["schema"]["properties"]
        if "translations" in properties:
            answer = {"translations": translate(json.loads(kwargs["input"])["items"])}
        elif "judgements" in properties or "usage" in properties:
            answer = judge(kwargs)
        else:
            answer = analysis
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(answer, ensure_ascii=False),
            usage=SimpleNamespace(input_tokens=100, output_tokens=10),
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create))


def detectors(client, languages=("kk",)):
    judge = OpenAIDetector("gpt-4o", "k", client, strategy="zero_shot", temperature=0.0, top_p=None)
    return OpenAIDetector(
        "gpt-4o-mini",
        "k",
        client,
        strategy="zero_shot",
        usage_judge=UsageJudge(judge, languages),
    )


def test_direct_question_is_the_measured_one():
    assert direct_question("Ай жүзді қыз", 3, 8, "жүз") == (
        "Word: жүз\nQuotation (word marked with [[ ]]):\nАй [[жүзді]] қыз"
    )
    assert direct_question("Ай жүзді қыз", 3, 8).startswith("Word: жүзді\n")


def test_stage_two_adds_figures_and_flags_literal_head_words():
    calls = []
    judge = lambda kwargs: {  # noqa: E731
        "judgements": [
            {"id": 2, "usage": "literal", "reason": "Камень здесь в прямом значении."},
            {"id": 1, "usage": "metaphorical", "reason": "Волк обозначает храброго воина."},
        ]
    }
    analysis = llm_payload(FIGURE, literal=[WOLF], language="kk")
    detector = detectors(fake_client(analysis, judge, calls))
    result = detector.analyze(TEXT, "kk")

    request = calls[1]
    assert request["model"] == "gpt-4o" and request["temperature"] == 0.0
    assert request["text"]["format"]["schema"] == BATCH_SCHEMA
    assert request["instructions"].startswith(INSTRUCTIONS) and "Russian" in request["instructions"]
    assert "1. Word: бөрі\n   Line: Тау басында [[бөрі]] ұлыды," in request["input"]
    assert "2. Word: тас\n" in request["input"] and "[[тас]]" in request["input"]

    wolf, heart = result.metaphors
    assert (wolf.text, wolf.label, wolf.entity, wolf.source_domain) == (
        "бөрі",
        "metaphor",
        "бөрі",
        "unknown",
    )
    assert wolf.rationale == "Волк обозначает храброго воина." and wolf.confidence == 0.5
    # The stage-1 figure stays: its head word judged literal only raises a warning.
    assert heart.text == "жүрегі тас"
    assert any("«тас»" in w and "literal" in w for w in result.warnings)
    usage = {c.text: (c.usage_type, c.reasoning) for c in result.candidates}
    assert usage["тас"] == ("literal", "Камень здесь в прямом значении.")
    assert usage["бөрі"][0] == "metaphorical"

    record = result.method["two_stage"]
    assert record["model"] == "openai:gpt-4o"
    assert (record["candidates"], record["judged"], record["metaphorical"]) == (2, 2, 1)
    assert record["added"] == [[12, 16]] and record["disputed"] == [[24, 34]]
    assert record["temperature"] == 0.0
    assert record["usage"] == {"requests": 1, "input_tokens": 100, "output_tokens": 10}
    assert result.method["usage"]["requests"] == 1  # stage 1 is counted separately
    assert reliability({"p": result})["two_stage_mean_input_tokens"] == 100
    assert len(calls) == 2


def test_single_candidate_temperature_fallback_and_russian_pass():
    calls = []

    def judge(kwargs):
        if "temperature" in kwargs:
            raise ValueError("Unsupported parameter: 'temperature' is not supported")
        return {"usage": "metaphorical", "reason": "Бөрі мұнда батыр адамды білдіреді."}

    def translate(items):
        return ["Волк здесь означает батыра." for _ in items]

    analysis = llm_payload(literal=[WOLF], language="kk")
    detector = detectors(fake_client(analysis, judge, calls, translate))
    result = detector.analyze(TEXT, "kk")

    asked = calls[2]
    assert asked["text"]["format"]["schema"] == SCHEMA and "temperature" not in asked
    assert asked["input"] == direct_question(TEXT, 12, 16)
    assert result.method["two_stage"]["temperature"] is None
    # The Kazakh reason was translated by the main detector's Russian pass.
    assert [m.rationale for m in result.metaphors] == ["Волк здесь означает батыра."]
    assert result.candidates[0].reasoning == "Волк здесь означает батыра."
    assert not any("could not be translated" in w for w in result.warnings)


def test_other_languages_keep_the_single_pass():
    calls = []
    detector = detectors(fake_client(llm_payload(llm_item()), None, calls))
    result = detector.analyze("心海", "zh")
    assert len(calls) == 1 and "two_stage" not in result.method


def test_failed_or_missing_judgements_keep_stage_one_decisions():
    calls = []

    def judge(kwargs):
        raise RuntimeError("network down")

    analysis = llm_payload(FIGURE, literal=[WOLF], language="kk")
    result = detectors(fake_client(analysis, judge, calls)).analyze(TEXT, "kk")
    assert [m.text for m in result.metaphors] == ["жүрегі тас"]
    assert [c.usage_type for c in result.candidates] == ["literal", "metaphorical"]
    assert result.method["two_stage"]["failed_requests"] == 1
    assert any("Stage 2 failed for 2 candidate(s)" in w for w in result.warnings)

    # An answer that skips an id leaves that candidate unjudged.
    partial = lambda kwargs: {  # noqa: E731
        "judgements": [{"id": 1, "usage": "metaphorical", "reason": "Волк — образ воина."}]
    }
    result = detectors(fake_client(analysis, partial, [])).analyze(TEXT, "kk")
    assert result.method["two_stage"]["judged"] == 1
    assert [m.text for m in result.metaphors] == ["бөрі", "жүрегі тас"]
    assert not result.method["two_stage"]["disputed"]


def test_calibrator_skips_added_figures_and_keeps_disputes_for_review():
    from app.nlp.calibration import Calibrator, platt
    from app.schemas.analysis import AnalysisResult

    def figure(text, start, confidence):
        return {
            "text": text,
            "start": start,
            "end": start + len(text),
            "label": "metaphor",
            "source_domain": "unknown",
            "target_domain": "unknown",
            "confidence": confidence,
            "rationale": "Образ.",
        }

    result = AnalysisResult(
        language="kk",
        model_version="openai:m",
        metaphors=[figure("бөрі", 12, 0.5), figure("жүрегі тас", 24, 0.99)],
        method={"two_stage": {"added": [[12, 16]], "disputed": [[24, 34]]}},
    )
    fit = {"a": 1.0, "b": 0.0, "source": "dictionary", "spans": 40}
    calibrated = Calibrator({"openai:m": {"kk": fit}}, threshold=0.5).apply(result)
    assert calibrated.metaphors[0].confidence == 0.5  # placeholder, not rescaled
    assert calibrated.metaphors[1].confidence == round(platt(0.99, 1.0, 0.0), 3)
    # No figure is below the threshold, yet the disputed head word still asks for a reviewer.
    assert calibrated.needs_review


def test_build_llm_wires_the_judge_only_when_configured():
    from app.core.config import Settings
    from app.nlp.pipeline import build_llm

    settings = Settings(_env_file=None, openai_api_key="k", openai_model="gpt-4o-mini")
    detector = build_llm(settings, "openai", "zero_shot")
    judge = detector.usage_judge
    assert judge.languages == {"kk"} and judge.detector.model == "gpt-4o"
    assert (judge.detector.temperature, judge.detector.top_p) == (0.0, None)
    assert detector.model == "gpt-4o-mini"

    off = settings.model_copy(update={"nlp_two_stage_languages": ""})
    assert build_llm(off, "openai", "zero_shot").usage_judge is None
    with pytest.raises(ValueError, match="NLP_TWO_STAGE_LANGUAGES"):
        build_llm(settings.model_copy(update={"nlp_two_stage_languages": "kk,en"}), "openai")
    no_key = settings.model_copy(update={"openai_api_key": None})
    with pytest.raises(ValueError, match="two-stage"):
        build_llm(no_key, "anthropic", "zero_shot")


def test_dictionary_score_reports_stage_two_decisions():
    from scripts.eval_kk_usage import evaluate_predictions

    records = {
        "a": {"start": 0, "end": 4, "usage_type": "metaphorical"},
        "b": {"start": 0, "end": 4, "usage_type": "literal"},
    }

    def prediction(figures, candidates):
        return {
            "metaphors": [{"start": 0, "end": 4}] if figures else [],
            "candidates": [{"start": 0, "end": 4, "usage_type": u} for u in candidates],
            "method": {
                "usage": {"input_tokens": 1000, "output_tokens": 100},
                "two_stage": {
                    "model": "openai:gpt-4o",
                    "usage": {"input_tokens": 200, "output_tokens": 20},
                },
            },
        }

    # "b": a stage-1 figure kept with a warning although stage 2 judged the headword literal.
    report = evaluate_predictions(
        records,
        {
            "a": prediction(True, ["metaphorical"]),
            "b": prediction(True, ["literal"]),
            "c": {"error": "x"},
        },
    )
    assert report["quotations"] == 2 and report["false_alarm_on_literal"] == 1.0
    assert report["mean_tokens"] == [1200, 120]
    stage = report["two_stage"]
    assert stage["model"] == "openai:gpt-4o" and stage["headword_is_candidate"] == 1.0
    assert stage["stage_2_decides"]["accuracy"] == 1.0
    assert stage["headword_candidates_only"]["quotations"] == 2
