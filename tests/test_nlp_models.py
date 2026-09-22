import json
from types import SimpleNamespace

import numpy as np
import pytest

from app.nlp.comparison import CrossLanguageMatcher
from app.nlp.hybrid import HybridDetector
from app.nlp.llm import OpenAIDetector, OllamaDetector, parse_output
from app.nlp.xlmr import align_labels, decode_bio, token_windows
from app.schemas.analysis import AnalysisResult
from app.schemas.comparison import ComparisonItem
from tests.test_nlp_contracts import poem, span


def test_alignment_and_windows_cover_tail():
    text = "心海 明月"
    offsets = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    assert align_labels(text, offsets, [span()]) == [1, 2, 0, 0, 0]
    with pytest.raises(ValueError, match="boundary"):
        align_labels("心海", [(0, 2)], [span(text="海", start=1)])
    tokenizer = SimpleNamespace(bos_token_id=0, eos_token_id=2)
    windows = list(token_windows(list(range(5)), offsets, tokenizer, max_length=5, stride=1))
    assert [(s, e) for s, e, _ in windows] == [(0, 3), (2, 5)]
    assert windows[-1][2]["input_ids"] == [0, 2, 3, 4, 2]
    with pytest.raises(ValueError):
        list(token_windows([1], [(0, 1)], tokenizer, 5, 3))


def test_bio_repair_adjacent_and_whitespace():
    spans = decode_bio(
        "心海 月",
        [(0, 1), (1, 2), (2, 4)],
        ["I-METAPHOR", "I-METAPHOR", "B-METAPHOR"],
        [0.8, 0.6, 0.9],
    )
    assert [(s.text, s.start, s.end) for s in spans] == [("心海", 0, 2), ("月", 3, 4)]


def test_hybrid_disagreement_does_not_become_confident_gold():
    primary = AnalysisResult(language="zh", model_version="xlmr", metaphors=[span()])
    secondary = AnalysisResult(
        language="zh", model_version="llm", metaphors=[span(text="海", start=1)]
    )

    def detector(result):
        return SimpleNamespace(analyze=lambda *_: result)

    result = HybridDetector(detector(primary), detector(secondary)).analyze("心海", "zh")
    assert result.needs_review and len(result.metaphors) == 1
    assert any("Conflicting" in w for w in result.warnings)
    negative = AnalysisResult(language="zh", model_version="xlmr", metaphors=[])
    result = HybridDetector(detector(negative), detector(primary)).analyze("心海", "zh")
    assert len(result.metaphors) == 1 and any("LLM-only" in w for w in result.warnings)


def test_openai_adapter_uses_schema_and_rejects_incomplete():
    captured = {}
    calls = 0

    def create(**kwargs):
        nonlocal calls
        calls += 1
        captured.update(kwargs)
        if calls == 2:
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"translations": ["Образ моря передаёт внутреннее переживание лирического героя."]}),
            )
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps({"language": "zh", "metaphors": [span().model_dump()]}),
        )

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = OpenAIDetector("test", "test", client).analyze("心海", "zh")
    assert result.model_version == "openai:test"
    assert captured["text"]["format"]["strict"] is True
    assert "in Russian" in captured["instructions"]
    assert "exclusively in Russian" in captured["text"]["format"]["schema"]["$defs"]["ModelSpan"]["properties"]["rationale"]["description"]
    assert json.loads(captured["input"])["poem"] == "心海"
    assert result.metaphors[0].rationale.startswith("Образ моря")
    client.responses.create = lambda **_: SimpleNamespace(status="incomplete")
    with pytest.raises(ValueError):
        OpenAIDetector("test", "test", client).analyze("心海", "zh")


def test_parse_output_repairs_wrong_offsets_only_for_unique_exact_span():
    raw = json.dumps({"language": "zh", "metaphors": [span().model_dump()]})
    result = parse_output(raw, "前心海", "zh", "test")
    assert [(item.text, item.start, item.end) for item in result.metaphors] == [("心海", 1, 3)]

    ambiguous = parse_output(raw, "心海和心海", "zh", "test")
    assert ambiguous.metaphors == []
    assert "omitted" in ambiguous.warnings[-1]


def test_ollama_http_adapter(monkeypatch):
    import io
    import app.nlp.llm as module

    captured = {}

    def send(request, timeout):
        captured.update(json.loads(request.data))
        return io.BytesIO(
            json.dumps(
                {
                    "done": True,
                    "done_reason": "stop",
                    "message": {"content": json.dumps({"language": "zh", "metaphors": []})},
                }
            ).encode()
        )

    monkeypatch.setattr(module, "urlopen", send)
    result = OllamaDetector("test").analyze("明月", "zh")
    assert not result.metaphors and captured["stream"] is False
    assert captured["format"]["additionalProperties"] is False
    with pytest.raises(ValueError, match="context budget"):
        OllamaDetector("test").analyze("心" * 10000, "zh")


def test_cross_language_ranking_and_e5_prefix():
    class Encoder:
        def encode(self, texts, **kwargs):
            assert all(t.startswith("query: ") for t in texts)
            return np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.8, 0.2]])

    matcher = CrossLanguageMatcher(encoder=Encoder())
    query = ComparisonItem(id="q", text="河", language="zh")
    candidates = [
        ComparisonItem(id="same", text="河", language="zh"),
        ComparisonItem(id="b", text="от", language="kk"),
        ComparisonItem(id="a", text="өзен", language="kk"),
    ]
    result = matcher.compare([query], candidates, 5)
    assert [m.candidate_id for m in result.matches] == ["a", "b"]
    assert result.matches[0].rank == 1


def test_attribute_training_roundtrip(tmp_path):
    from app.nlp.attributes import AttributeClassifier, train_attributes

    records = [
        poem(spans=[span()]),
        poem(
            "低语",
            id="2",
            work_id="2",
            spans=[
                span(
                    text="低语",
                    label="personification",
                    source_domain="person",
                    target_domain="nature",
                )
            ],
        ),
    ]
    train_attributes(records, tmp_path / "attributes", allow_synthetic=True)
    classifier = AttributeClassifier(tmp_path / "attributes")
    result = classifier.classify(
        "心海", AnalysisResult(language="zh", model_version="test", metaphors=[span()])
    )
    assert result.metaphors[0].source_domain in {"water", "person"}
    assert result.metaphors[0].confidence <= 0.5


def test_real_tiny_xlmr_train_save_load_infer(tmp_path):
    """Actual transformers/PyTorch execution on random tiny weights, no downloads."""
    transformers = pytest.importorskip("transformers")
    pytest.importorskip("torch")
    from tokenizers import Tokenizer, models, pre_tokenizers
    from app.nlp.corpus import write_corpus
    from app.nlp.training import train_xlmr
    from app.nlp.xlmr import XLMRDetector

    vocab = {
        word: i
        for i, word in enumerate(
            ["<s>", "<pad>", "</s>", "<unk>", "<mask>", "心海", "明月", "风", "低语", "山"]
        )
    }
    backend = Tokenizer(models.WordLevel(vocab, unk_token="<unk>"))
    backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    tokenizer = transformers.XLMRobertaTokenizerFast(tokenizer_object=backend, model_max_length=64)
    config = transformers.XLMRobertaConfig(
        vocab_size=len(vocab),
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        max_position_embeddings=66,
        num_labels=3,
        id2label={0: "O", 1: "B-METAPHOR", 2: "I-METAPHOR"},
        label2id={"O": 0, "B-METAPHOR": 1, "I-METAPHOR": 2},
    )
    base = tmp_path / "base"
    transformers.XLMRobertaForTokenClassification(config).save_pretrained(base)
    tokenizer.save_pretrained(base)
    train = [poem("心海 明月", spans=[span()]), poem("明月 山", id="neg", work_id="neg")]
    validation = [poem("心海 山", id="val", work_id="val", spans=[span()])]
    write_corpus(tmp_path / "train.jsonl", train)
    write_corpus(tmp_path / "validation.jsonl", validation)
    output = tmp_path / "trained"
    meta = train_xlmr(
        tmp_path / "train.jsonl",
        tmp_path / "validation.jsonl",
        output,
        model_name=str(base),
        epochs=1,
        batch_size=2,
        max_length=8,
        stride=2,
        allow_synthetic=True,
        device="cpu",
    )
    result = XLMRDetector(str(output), max_length=8, stride=2, device="cpu").analyze(
        "心海 明月 " * 15, "zh"
    )
    assert meta["history"][0]["epoch"] == 1
    assert result.model_version == meta["model_version"]
    assert (output / "experiment.json").exists()

    # Exercise the real sentence-transformers wrapper on the same tiny local backbone.
    from sentence_transformers import SentenceTransformer, models as st_models

    transformer = st_models.Transformer(str(output), max_seq_length=16)
    encoder = SentenceTransformer(modules=[transformer, st_models.Pooling(16)], device="cpu")
    matches = CrossLanguageMatcher("tiny-random-test", encoder=encoder).compare(
        [ComparisonItem(id="zh", text="心海", language="zh")],
        [ComparisonItem(id="kk", text="өзен", language="kk")],
        k=1,
    )
    assert len(matches.matches) == 1
