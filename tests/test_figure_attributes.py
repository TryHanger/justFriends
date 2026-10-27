"""Type and domain heads for XLM-R spans, without model weights or PyTorch."""

import pytest

from app.nlp.figure_attributes import FigureAttributes, annotate, explanation, simile_marker
from app.schemas.analysis import AnalysisResult, MetaphorSpan

ZH = "方丈叹了一口气：你执着追求那些世俗的欲望，就如同镜中之花，水中之月。"
KK = "Жүректе көп қазына бар, Теңіздің түбіндей-ақ қарап бақшы. Бұл сияқты сөз жоқ."


def span(text, poem=ZH, **fields):
    start = poem.index(text)
    values = dict(
        label="metaphor",
        source_domain="unknown",
        target_domain="unknown",
        confidence=0.9,
        rationale="XLM-R",
    )
    values.update(fields)
    return MetaphorSpan(text=text, start=start, end=start + len(text), **values)


def test_comparison_markers_in_both_languages():
    s = span("镜中之花")
    assert simile_marker(ZH, s.start, s.end, "zh") == "如同"
    s = span("世俗的欲望")
    assert simile_marker(ZH, s.start, s.end, "zh") is None
    s = span("Теңіздің түбіндей-ақ", KK)
    assert simile_marker(KK, s.start, s.end, "kk") == "түбіндей-ақ"
    s = span("сөз", KK)  # the comparison word right before the span
    assert simile_marker(KK, s.start, s.end, "kk") == "сияқты"
    s = span("көп қазына", KK)
    assert simile_marker(KK, s.start, s.end, "kk") is None


def test_marker_makes_a_simile_and_weak_domains_stay_unknown():
    predicted = {
        "label": ("metaphor", 0.8),
        "source_domain": ("plant", 0.45),
        "target_domain": ("emotion", 0.2),
    }
    result = annotate(span("镜中之花"), predicted, "如同")
    assert (result.label, result.source_domain, result.target_domain) == (
        "simile",
        "plant",
        "unknown",
    )
    assert result.rationale == (
        "«镜中之花» — сравнение: образ из области «растение»; на что он переносится, "
        "модель не определила. Сравнение выражено словом «如同». "
        "Области определены предположительно."
    )


def test_confident_prediction_has_a_plain_explanation():
    predicted = {
        "label": ("personification", 0.9),
        "source_domain": ("person", 0.8),
        "target_domain": ("nature", 0.7),
    }
    result = annotate(span("水中之月"), predicted, None)
    assert result.label == "personification"
    assert result.rationale == (
        "«水中之月» — олицетворение: свойства человека переносятся на область «природа»."
    )


def test_explanation_without_domains():
    s = span("水中之月", source_domain="unknown", target_domain="unknown")
    assert (
        explanation(s, None, False) == "«水中之月» — метафора; области образа модель не определила."
    )


def test_heads_pick_the_most_probable_class(tmp_path):
    np = pytest.importorskip("numpy")
    heads = {
        "label": {
            "classes": ["metaphor", "simile"],
            "coef": [[1.0, 0.0], [0.0, 1.0]],
            "intercept": [0.0, 0.0],
            "mean": [0.0, 0.0],
            "scale": [1.0, 1.0],
        }
    }
    path = tmp_path / "figure_attributes.json"
    path.write_text(
        '{"layers": [12], "heads": ' + __import__("json").dumps(heads) + "}", encoding="utf-8"
    )
    model = FigureAttributes.load(path)
    label, probability = model.predict(np.array([0.0, 3.0]))["label"]
    assert label == "simile" and probability > 0.9
    assert FigureAttributes.load(tmp_path / "missing.json") is None


def test_calibrated_xlmr_result_with_attributes_has_no_extra_warnings():
    from app.nlp.calibration import XLMR_PROBABILITIES, Calibrator

    result = AnalysisResult(
        language="zh",
        model_version="xlmr-v1-x",
        warnings=[XLMR_PROBABILITIES],
        metaphors=[span("镜中之花")],
    )
    fit = {"a": 1.0, "b": 0.5, "source": "CMDAG", "spans": 1000}
    calibrated = Calibrator({"xlmr-v1-x": {"zh": fit}}, threshold=0.8).apply(result)
    assert calibrated.warnings == [
        "Confidence calibrated on CMDAG (1000 figures): the probability that a figure is correct."
    ]
    assert calibrated.needs_review is False


def test_unified_keeps_the_xlmr_type_and_explanation_with_attributes():
    from app.nlp.unified import XLMR_ONLY, merge

    figure = span(
        "镜中之花", label="simile", source_domain="plant", rationale="«镜中之花» — сравнение."
    )
    xlmr = AnalysisResult(
        language="zh",
        model_version="xlmr",
        metaphors=[figure],
        method={"attributes": {"method": "heads"}},
    )
    llm = AnalysisResult(language="zh", model_version="llm", metaphors=[])
    merged = merge(ZH, "zh", llm, xlmr, 0.8)
    only = merged.metaphors[0]
    assert (only.label, only.source_domain) == ("simile", "plant")
    assert only.rationale == f"{XLMR_ONLY} «镜中之花» — сравнение."
    assert not any("review threshold" in w for w in merged.warnings)
