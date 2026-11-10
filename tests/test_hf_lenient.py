from app.nlp.hf_local import coerce_enums
from app.nlp.llm import output_schema


def figure(**changes):
    item = {
        "text": "бүркіт",
        "start": 0,
        "end": 6,
        "basic_meaning": "хищная птица",
        "contextual_meaning": "герой",
        "contrast": "птица и человек",
        "entity": "бүркіт",
        "entity_type": "animal",
        "tenor": "",
        "ground": "сила",
        "label": "metaphor",
        "source_domain": "animal",
        "target_domain": "person",
        "confidence": 0.8,
        "rationale": "герой назван птицей",
        "semantic_label": "герой",
        "sentiment": "positive",
    }
    return {**item, **changes}


def test_out_of_list_domain_becomes_other():
    answer = {"language": "kk", "metaphors": [figure(source_domain="abstract")]}
    fixed, repairs = coerce_enums(answer, output_schema(True))
    assert fixed["metaphors"][0]["source_domain"] == "other"
    assert repairs == 1


def test_item_without_fallback_is_dropped_not_the_answer():
    # A literal reading put among the figures: "literal" is not a figure label.
    answer = {"language": "kk", "metaphors": [figure(), figure(label="literal")]}
    fixed, repairs = coerce_enums(answer, output_schema(True))
    assert [m["label"] for m in fixed["metaphors"]] == ["metaphor"]
    assert repairs == 1


def test_valid_answer_is_unchanged():
    answer = {"language": "kk", "metaphors": [figure()]}
    assert coerce_enums(answer, output_schema(True)) == (answer, 0)
