"""Unified profile with fake detectors: no model weights, PyTorch or provider calls."""

import pytest

from app.nlp.unified import XLMR_ONLY, UnifiedPipeline, merge
from app.schemas.analysis import AnalysisResult, EntityCandidate, MetaphorSpan, StanzaLabel

POEM = "春风又绿江南岸，明月何时照我还。"
CALIBRATED = (
    "Confidence calibrated on CMDAG (100 figures): the probability that a figure is correct."
)
SHARED = "Shared warning."


def span(text, confidence, **fields):
    start = POEM.index(text)
    values = dict(
        label="metaphor",
        source_domain="unknown",
        target_domain="unknown",
        rationale="XLM-R detected a metaphor; type and domains need classification.",
    )
    values.update(fields)
    return MetaphorSpan(
        text=text, start=start, end=start + len(text), confidence=confidence, **values
    )


def candidate(text, entity_type):
    start = POEM.index(text)
    return EntityCandidate(text=text, start=start, end=start + len(text), entity_type=entity_type)


def llm_result(**update):
    result = AnalysisResult(
        language="zh",
        model_version="openai:gpt-4o-mini",
        metaphors=[
            span(
                "春风又绿",
                0.6,
                label="personification",
                source_domain="person",
                target_domain="nature",
                rationale="Весенний ветер «озеленяет» берег, как человек.",
                tenor="春风",
                ground="使变绿",
            ),
            span("明月", 0.9, source_domain="light", target_domain="emotion", rationale="Луна."),
        ],
        needs_review=False,
        warnings=[
            CALIBRATED,
            "1 of 2 figure(s) below the review threshold 80%: check them first.",
            SHARED,
        ],
        candidates=[candidate("明月", "celestial")],
        method={
            "strategy": "zero_shot",
            "calibration": {"method": "platt", "raw_confidence": [0.7, 0.95]},
        },
        stanzas=[
            StanzaLabel(
                text=POEM,
                start=0,
                end=len(POEM),
                label="賦",
                probabilities={"賦": 0.6, "比": 0.2, "興": 0.2},
            )
        ],
    )
    return result.model_copy(update=update)


def xlmr_result(**update):
    result = AnalysisResult(
        language="zh",
        model_version="xlmr-zh-gold-v2",
        # 绿江南 overlaps the LLM figure 春风又绿 with a higher confidence; 照我 is XLM-R only.
        metaphors=[span("绿江南", 0.85), span("照我", 0.4)],
        needs_review=True,
        warnings=[
            "XLM-R does not determine source and target domains.",
            "1 of 2 figure(s) below the review threshold 80%: check them first.",
            SHARED,
        ],
        candidates=[candidate("明月", "celestial"), candidate("江南", "landscape")],
        method={"calibration": {"method": "platt", "source": "CMDAG"}},
    )
    return result.model_copy(update=update)


def test_merge_keeps_llm_figures_and_adds_xlmr_only_ones():
    result = merge(POEM, "zh", llm_result(), xlmr_result(), 0.8)

    assert [(m.text, m.confidence) for m in result.metaphors] == [
        ("春风又绿", 0.85),  # found by both: LLM figure, larger calibrated confidence
        ("明月", 0.9),
        ("照我", 0.4),
    ]
    both, llm_only, xlmr_only = result.metaphors
    assert (both.label, both.source_domain, both.tenor, both.ground) == (
        "personification",
        "person",
        "春风",
        "使变绿",
    )
    assert both.rationale.startswith("Весенний ветер")
    assert llm_only == llm_result().metaphors[1]
    assert (xlmr_only.label, xlmr_only.source_domain, xlmr_only.target_domain) == (
        "metaphor",
        "unknown",
        "unknown",
    )
    assert xlmr_only.rationale == XLMR_ONLY

    unified = result.method["unified"]
    assert unified["sources"] == {"0-4": ["llm", "xlmr"], "8-10": ["llm"], "12-14": ["xlmr"]}
    assert (unified["both"], unified["llm_only"], unified["xlmr_only"]) == (1, 1, 1)
    assert unified["xlmr_model"] == "xlmr-zh-gold-v2"
    assert result.method["model_profile"] == "unified"
    assert result.method["strategy"] == "zero_shot"
    assert result.method["xlmr"]["calibration"]["source"] == "CMDAG"
    # Self-reported LLM values follow the merged figures; XLM-R-only figures have none.
    assert result.method["calibration"]["raw_confidence"] == [0.7, 0.95, None]
    assert result.model_version == "unified(openai:gpt-4o-mini,xlmr-zh-gold-v2)"

    # Per-part review summaries are replaced by one for the merged figures; no duplicates.
    assert result.warnings == [
        CALIBRATED,
        SHARED,
        "XLM-R does not determine source and target domains.",
        "1 of 3 figure(s) below the review threshold 80%: check them first.",
    ]
    assert result.needs_review is True  # the XLM-R part needs review
    assert [(c.text, c.entity_type) for c in result.candidates] == [
        ("明月", "celestial"),
        ("江南", "landscape"),
    ]
    assert result.stanzas == llm_result().stanzas


def test_merge_needs_review_only_when_a_part_needs_it():
    xlmr = xlmr_result(needs_review=False, metaphors=[span("绿江南", 0.85)])
    result = merge(POEM, "zh", llm_result(), xlmr, 0.8)
    assert result.needs_review is False
    assert result.method["unified"]["sources"] == {"0-4": ["llm", "xlmr"], "8-10": ["llm"]}


def test_xlmr_figure_overlapping_two_llm_figures_counts_for_both():
    xlmr = xlmr_result(metaphors=[span("绿江南岸，明月", 0.3)])
    result = merge(POEM, "zh", llm_result(), xlmr, 0.8)
    assert [(m.text, m.confidence) for m in result.metaphors] == [("春风又绿", 0.6), ("明月", 0.9)]
    assert result.method["unified"]["both"] == 2
    assert result.method["unified"]["xlmr_only"] == 0


class FakePipeline:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def analyze(self, text, language="auto"):
        self.calls.append(language)
        if self.error:
            raise self.error
        return self.result


def test_pipeline_runs_xlmr_of_the_detected_language():
    llm, xlmr = FakePipeline(llm_result()), FakePipeline(xlmr_result())
    requested = []

    def xlmr_for(language):
        requested.append(language)
        return lambda text: xlmr.analyze(text, language)

    result = UnifiedPipeline(llm, xlmr_for).analyze(POEM, "auto")
    assert llm.calls == ["auto"] and requested == ["zh"] and xlmr.calls == ["zh"]
    assert result.method["unified"]["both"] == 1


def test_pipeline_skips_unavailable_xlmr_with_a_warning():
    result = UnifiedPipeline(FakePipeline(llm_result()), lambda language: None).analyze(POEM, "zh")
    assert [m.text for m in result.metaphors] == ["春风又绿", "明月"]
    assert [m.confidence for m in result.metaphors] == [0.6, 0.9]
    assert result.method["unified"]["sources"] == {"0-4": ["llm"], "8-10": ["llm"]}
    assert result.method["unified"]["xlmr_model"] is None
    assert "xlmr" not in result.method
    assert result.model_version == "unified(openai:gpt-4o-mini)"
    assert (
        "Unified model: XLM-R for zh is not installed (weights or PyTorch missing); "
        "only LLM figures are shown." in result.warnings
    )
    assert result.needs_review is False


def test_pipeline_keeps_llm_figures_when_xlmr_fails():
    broken = FakePipeline(error=OSError("bad checkpoint"))
    result = UnifiedPipeline(
        FakePipeline(llm_result()), lambda language: lambda text: broken.analyze(text, language)
    ).analyze(POEM, "zh")
    assert [m.text for m in result.metaphors] == ["春风又绿", "明月"]
    assert (
        "Unified model: XLM-R for zh failed (OSError); only LLM figures are shown."
        in result.warnings
    )


@pytest.fixture
def analyzer(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import analyzer

    monkeypatch.setenv("NLP_BACKEND", "openai")
    monkeypatch.setenv("CHINESE_GOLD_XLMR_MODEL_PATH", str(tmp_path / "zh"))
    monkeypatch.setenv("EXPERIMENTAL_KK_XLMR_MODEL_PATH", str(tmp_path / "kk"))
    get_settings.cache_clear()
    analyzer.get_pipeline.cache_clear()
    built = []

    def build_pipeline(settings):
        built.append(settings.nlp_backend)
        if settings.nlp_backend == "xlmr":
            assert settings.xlmr_model_path == str(tmp_path / "zh")
            return FakePipeline(xlmr_result(model_version="xlmr:zh"))
        return FakePipeline(llm_result())

    monkeypatch.setattr(analyzer, "build_pipeline", build_pipeline)
    analyzer.built = built
    yield analyzer
    analyzer.get_pipeline.cache_clear()
    get_settings.cache_clear()


def test_unified_profile_uses_the_profiled_xlmr_pipeline(analyzer, monkeypatch):
    monkeypatch.setattr(analyzer, "checkpoint_ready", lambda path: path.endswith("zh"))
    result = analyzer.analyze_text(POEM, "zh", "unified")
    assert result.model_version == "unified(openai:gpt-4o-mini,xlmr-zh-gold-v2)"
    assert result.method["xlmr"]["model_profile"] == "xlmr_zh_gold_v2"
    assert [m.text for m in result.metaphors] == ["春风又绿", "明月", "照我"]
    # The default and XLM-R pipelines are shared with their own profiles, built once.
    analyzer.analyze_text(POEM, "zh", "unified")
    assert analyzer.built == ["openai", "xlmr"]


def test_unified_profile_without_weights_runs_the_llm_only(analyzer, monkeypatch):
    monkeypatch.setattr(analyzer, "checkpoint_ready", lambda path: False)
    result = analyzer.analyze_text(POEM, "zh", "unified")
    assert result.method["unified"]["xlmr_model"] is None
    assert analyzer.built == ["openai"]


def test_unified_profile_needs_an_llm_backend(analyzer, monkeypatch):
    monkeypatch.setenv("NLP_BACKEND", "baseline")
    analyzer.get_settings.cache_clear()
    with pytest.raises(analyzer.AnalyzerNotConfigured):
        analyzer.get_pipeline("unified")


def test_catalog_offers_unified_with_an_openai_key(monkeypatch):
    from app.api.v1.routes import analyses
    from app.schemas.analysis import AnalyzeRequest

    def entry():
        return {model.id: model for model in analyses.list_models()}["unified"]

    monkeypatch.setattr(analyses.settings, "openai_api_key", None)
    assert entry().available is False
    monkeypatch.setattr(analyses.settings, "openai_api_key", "sk-test")
    model = entry()
    assert model.available is True
    assert model.name == "Единая модель"
    assert model.languages == ["auto", "zh", "kk"]
    assert AnalyzeRequest(text=POEM, model_profile="unified").model_profile == "unified"
