import json
from types import SimpleNamespace

from app.nlp.allegory import AllegoryJudge, is_classical
from app.nlp.llm import OpenAIDetector
from tests.test_nlp_contracts import llm_item, llm_payload

# 荃 (a fragrant herb) stands for the ruler in Wang Yi's reading of 离骚.
POEM = "荃不察余之中情兮，反信谗而齌怒。余固知謇謇之为患兮，忍而不能舍也。"


def fake_client(images, calls):
    def create(**kwargs):
        calls.append(kwargs)
        properties = kwargs["text"]["format"]["schema"]["properties"]
        if "images" in properties:
            answer = {"images": images}
        elif "translations" in properties:
            items = json.loads(kwargs["input"])["items"]
            answer = {"translations": ["Перевод."] * len(items)}
        else:
            answer = llm_payload(llm_item("反信谗", 10, entity="谗"))
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(answer, ensure_ascii=False),
            usage=SimpleNamespace(input_tokens=100, output_tokens=10),
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create))


def detector(client):
    reader = OpenAIDetector(
        "gpt-4o-mini", "k", client, strategy="zero_shot", temperature=0.0, top_p=None
    )
    return OpenAIDetector(
        "gpt-4o-mini", "k", client, strategy="zero_shot", allegory_judge=AllegoryJudge(reader)
    )


def test_classical_detection():
    assert is_classical(POEM)  # 兮
    assert is_classical("关关雎鸠，在河之洲。窈窕淑女，君子好逑。参差荇菜，左右流之。")
    assert not is_classical("雪中送炭")  # too short
    assert not is_classical("他每天早上七点起床，然后坐地铁去公司上班，晚上很晚才回家休息。")


def test_classical_mode_adds_tradition_images_with_tenor():
    images = [
        {
            "text": "荃",
            "tenor": "君",
            "source_domain": "plant",
            "target_domain": "person",
            "explanation": "Благоуханная трава 荃 означает государя.",
        },
        {
            "text": "谗",
            "tenor": "谗人",
            "source_domain": "person",
            "target_domain": "society",
            "explanation": "Уже покрыто фигурой первого этапа.",
        },
        {
            "text": "凤凰",
            "tenor": "贤人",
            "source_domain": "animal",
            "target_domain": "person",
            "explanation": "Этого слова нет в тексте.",
        },
    ]
    calls = []
    result = detector(fake_client(images, calls)).analyze(POEM, "zh")
    added = [m for m in result.metaphors if m.text == "荃"]
    assert added and added[0].tenor == "君" and added[0].confidence == 0.5
    assert added[0].rationale.startswith("Благоуханная трава")
    assert [m.text for m in result.metaphors].count("谗") == 0  # overlap with 反信谗 skipped
    assert result.method["classical"]["added"] == [[0, 1]]
    assert result.needs_review and any("Classical poetry mode" in w for w in result.warnings)


def test_modern_text_and_kazakh_skip_the_classical_question():
    judge = AllegoryJudge(None)
    assert not judge.applies("zh", "他每天早上七点起床，然后坐地铁去公司上班，晚上很晚才回家休息。")
    assert not judge.applies("kk", POEM)


def test_calibrator_leaves_classical_images_alone():
    from app.nlp.calibration import Calibrator

    images = [
        {
            "text": "荃",
            "tenor": "君",
            "source_domain": "plant",
            "target_domain": "person",
            "explanation": "Государь.",
        }
    ]
    result = detector(fake_client(images, [])).analyze(POEM, "zh")
    fit = {"a": 1.0, "b": -1.0, "source": "CMDAG", "spans": 100}
    calibrated = Calibrator({result.model_version: {"zh": fit}}, threshold=0.8).apply(result)
    assert next(m for m in calibrated.metaphors if m.text == "荃").confidence == 0.5


def test_classical_image_overrides_a_literal_candidate():
    images = [
        {
            "text": "荃",
            "tenor": "君",
            "source_domain": "plant",
            "target_domain": "person",
            "explanation": "Благоуханная трава 荃 означает государя.",
        }
    ]

    def payload():
        literal = {
            "text": "荃",
            "start": 0,
            "end": 1,
            "entity_type": "plant",
            "reasoning": "Растение в прямом значении.",
        }
        return llm_payload(llm_item("反信谗", 10, entity="谗"), literal=[literal])

    calls = []
    client = fake_client(images, calls)
    original = client.responses.create

    def create(**kwargs):
        if (
            "images" in kwargs["text"]["format"]["schema"]["properties"]
            or "translations" in kwargs["text"]["format"]["schema"]["properties"]
        ):
            return original(**kwargs)
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(payload(), ensure_ascii=False),
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    client.responses.create = create
    result = detector(client).analyze(POEM, "zh")
    candidate = next(c for c in result.candidates if c.text == "荃")
    assert candidate.usage_type == "metaphorical" and "государя" in candidate.reasoning
