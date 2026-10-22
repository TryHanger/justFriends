"""Stanza types 賦/比/興 without model weights: splitting, conversion, pipeline wiring."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.nlp import stanza
from app.nlp.baseline import LexicalDetector
from app.nlp.pipeline import MetaphorPipeline
from app.nlp.stanza import StanzaClassifier, split_stanzas, to_traditional
from app.schemas.analysis import AnalysisResult, StanzaLabel

SIMPLIFIED = {"关": "關", "鸠": "鳩", "参": "參"}
TRADITIONAL = {v: k for k, v in SIMPLIFIED.items()}


class FakeConverter:
    def __init__(self, table):
        self.table = table

    def convert(self, text):
        return "".join(self.table.get(c, c) for c in text)


@pytest.fixture
def fake_opencc(monkeypatch):
    converters = FakeConverter(SIMPLIFIED), FakeConverter(TRADITIONAL)
    monkeypatch.setattr(stanza, "_converters", lambda: converters)


class FakeStanzaClassifier(StanzaClassifier):
    def __init__(self):
        self.labels, self.version, self.inputs = ["賦", "比", "興"], "fake-stanza", []

    def probabilities(self, texts):
        self.inputs.extend(texts)
        return [[0.1, 0.2, 0.7] if "鳩" in t else [0.6, 0.3, 0.1] for t in texts]


def test_split_on_blank_lines_with_offsets():
    text = "\n關關雎鳩，\n在河之洲。\r\n 　\r\n參差荇菜，\n\n\n左右流之。  \n"
    spans = split_stanzas(text)
    assert [text[s:e] for s, e in spans] == ["關關雎鳩，\n在河之洲。", "參差荇菜，", "左右流之。"]


def test_text_without_blank_lines_is_one_stanza():
    assert split_stanzas("  關關雎鳩，\n在河之洲。\n") == [(2, 13)]
    assert split_stanzas(" \n\n \n") == []


def test_only_simplified_text_is_converted(fake_opencc):
    assert to_traditional("关关雎鸠") == "關關雎鳩"
    assert to_traditional("關關雎鳩") == "關關雎鳩"
    assert to_traditional("在河之洲") == "在河之洲"


def test_real_opencc_conversion():
    pytest.importorskip("opencc")
    stanza._converters.cache_clear()
    assert to_traditional("关关雎鸠，在河之洲。") == "關關雎鳩，在河之洲。"
    # Traditional input stays untouched even where s2t would rewrite a character.
    assert to_traditional("關關雎鳩，后妃之德。") == "關關雎鳩，后妃之德。"


def test_classifier_labels_each_stanza_on_original_offsets(fake_opencc):
    classifier = FakeStanzaClassifier()
    text = "关关雎鸠，在河之洲。\n\n参差荇菜，左右流之。"
    labels = classifier.classify(text)
    assert classifier.inputs == ["關關雎鳩，在河之洲。", "參差荇菜，左右流之。"]
    assert [(x.text, x.start, x.end, x.label) for x in labels] == [
        ("关关雎鸠，在河之洲。", 0, 10, "興"),
        ("参差荇菜，左右流之。", 12, 22, "賦"),
    ]
    assert labels[0].probabilities == {"賦": 0.1, "比": 0.2, "興": 0.7}


def test_pipeline_adds_stanzas_for_chinese_only(fake_opencc):
    pipeline = MetaphorPipeline(LexicalDetector(), stanza=FakeStanzaClassifier())
    zh = pipeline.analyze("关关雎鸠，在河之洲。\n\n参差荇菜，左右流之。", "zh")
    assert [s.label for s in zh.stanzas] == ["興", "賦"]
    assert zh.method["stanza_model"] == "fake-stanza"
    kk = pipeline.analyze("Жүрегім менің жаралы", "kk")
    assert kk.stanzas == [] and "stanza_model" not in kk.method
    assert MetaphorPipeline(LexicalDetector()).analyze("关关雎鸠", "zh").stanzas == []


def test_missing_model_or_libraries_skip_the_classifier(tmp_path, monkeypatch):
    stanza.load_stanza_classifier.cache_clear()
    assert stanza.load_stanza_classifier(str(tmp_path / "absent")) is None
    assert not stanza.stanza_model_ready("")
    assert not stanza.stanza_model_ready(None)
    monkeypatch.setattr(stanza.importlib.util, "find_spec", lambda name: None)
    assert not stanza.stanza_model_ready(str(tmp_path))
    monkeypatch.setattr(stanza.importlib.util, "find_spec", lambda name: SimpleNamespace())
    assert stanza.stanza_model_ready(str(tmp_path))


def test_build_pipeline_without_stanza_model(tmp_path):
    from app.core.config import Settings
    from app.nlp.pipeline import build_pipeline

    settings = Settings(nlp_backend="baseline", stanza_model_path=str(tmp_path / "absent"))
    assert build_pipeline(settings).stanza is None


def test_schema_keeps_old_results_and_checks_stanzas():
    old = AnalysisResult.model_validate({"language": "zh", "model_version": "v", "metaphors": []})
    assert old.stanzas == []
    with pytest.raises(ValidationError):
        StanzaLabel(text="a", start=3, end=3, label="賦", probabilities={"賦": 1.0})
    with pytest.raises(ValidationError):
        StanzaLabel(text="a", start=0, end=1, label="風", probabilities={"賦": 1.0})
    with pytest.raises(ValidationError):
        StanzaLabel(text="a", start=0, end=1, label="賦", probabilities={"賦": 1.5})


def test_real_stanza_model():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("opencc")
    path = Path(__file__).resolve().parents[1] / "models/zhuxi-stanza-sikuroberta-v1"
    if not path.is_dir():
        pytest.skip("stanza model weights are not in the repository")
    labels = StanzaClassifier(path).classify("关关雎鸠，在河之洲。\n窈窕淑女，君子好逑。")
    assert len(labels) == 1 and labels[0].label in {"賦", "比", "興"}
    assert sum(labels[0].probabilities.values()) == pytest.approx(1, abs=1e-3)


def test_short_fragments_are_not_stanzas():
    from app.nlp.stanza import is_stanza

    assert not is_stanza("雪中送炭")  # an idiom, not a stanza
    assert not is_stanza("床前明月光")  # one verse
    assert is_stanza("盧令令、其人美且仁。")  # the shortest stanza type in training
    assert is_stanza("关关雎鸠，在河之洲。窈窕淑女，君子好逑。")
