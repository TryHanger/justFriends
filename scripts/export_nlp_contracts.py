"""Regenerate versioned integration artifacts: python -m scripts.export_nlp_contracts."""

from pathlib import Path
from xml.sax.saxutils import escape

from app.nlp.contracts import output_schema
from app.nlp.corpus import Poem, save_json
from app.schemas.analysis import AnalysisResult
from app.schemas.comparison import ComparisonItem, ComparisonResult
from app.schemas.taxonomy import (
    DOMAINS,
    ENTITY_TYPES,
    LABELS,
    METAPHOR_LABELS,
    SENTIMENTS,
    TAXONOMY_VERSION,
    USAGE_TYPES,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name, schema in {
        "llm-output": output_schema(),
        "llm-output-cot": output_schema(cot=True),
        "corpus": Poem.model_json_schema(),
        "analysis-result": AnalysisResult.model_json_schema(),
        "comparison-item": ComparisonItem.model_json_schema(),
        "comparison-result": ComparisonResult.model_json_schema(),
    }.items():
        save_json(ROOT / "contracts" / f"{name}.schema.json", schema)
    save_json(
        ROOT / "contracts/taxonomy.json",
        {
            "version": TAXONOMY_VERSION,
            "labels": list(LABELS),
            "domains": list(DOMAINS),
            "entity_types": list(ENTITY_TYPES),
            "usage_types": list(USAGE_TYPES),
            "sentiments": list(SENTIMENTS),
            "bio_positive_labels": sorted(METAPHOR_LABELS),
            "offset_unit": "unicode_codepoint",
            "end_exclusive": True,
        },
    )

    def options(values):
        return "".join(f'<Choice value="{escape(x)}"/>' for x in values)

    def region_choices(name, values, layout):
        # Long vocabularies as drop-downs keep the attribute column on one screen.
        return (
            f'<Choices name="{name}" toName="poem" perRegion="true" choice="single" '
            f'required="false" layout="{layout}" visibleWhen="region-selected">'
            f"{options(values)}</Choices>"
        )

    def region_text(name, placeholder):
        return (
            f'<TextArea name="{name}" toName="poem" perRegion="true" maxSubmissions="1" '
            f'editable="true" visibleWhen="region-selected" placeholder="{placeholder}"/>'
        )

    labels = "".join(f'<Label value="{escape(x)}"/>' for x in LABELS)
    # Two columns: labels above the poem on the left, attributes of the selected region on
    # the right, so long poems never push the controls below the fold.
    xml = (
        '<View style="display: flex; gap: 24px; align-items: flex-start">'
        '<View style="flex: 3; min-width: 0">'
        '<Header value="1. Выделите фрагмент и выберите метку" size="5"/>'
        f'<Labels name="figure" toName="poem">{labels}</Labels>'
        '<Labels name="entity" toName="poem"><Label value="entity"/></Labels>'
        '<Text name="poem" value="$text"/>'
        "</View>"
        '<View style="flex: 2; min-width: 280px; position: sticky; top: 0">'
        '<Header value="2. Поля выделенного фрагмента" size="5"/>'
        '<Header value="Для фигуры" size="6"/>'
        + region_choices("source_domain", DOMAINS, "select")
        + region_choices("target_domain", DOMAINS, "select")
        + region_choices("sentiment", SENTIMENTS, "inline")
        + region_text("semantic_label", "Семантическая метка по-русски, напр. благородный муж")
        + region_text("tenor", "Тема: что описывается, словами из текста")
        + region_text("ground", "Основание сравнения: общее свойство")
        + '<Header value="Для entity" size="6"/>'
        + region_choices("entity_type", ENTITY_TYPES, "select")
        + region_choices("usage_type", USAGE_TYPES, "inline")
        + "</View></View>\n"
    )
    target = ROOT / "annotation/label_studio.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(xml, encoding="utf-8")


if __name__ == "__main__":
    main()
