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

    def region_choices(name, values, required):
        return (
            f'<Choices name="{name}" toName="poem" perRegion="true" choice="single" '
            f'required="{str(required).lower()}" visibleWhen="region-selected">{options(values)}</Choices>'
        )

    labels = "".join(f'<Label value="{escape(x)}"/>' for x in LABELS)
    xml = (
        '<View><Text name="poem" value="$text"/>'
        f'<Header value="Фигура (выражение)"/><Labels name="figure" toName="poem">{labels}</Labels>'
        '<Header value="Сущность-кандидат (literal или metaphorical)"/>'
        '<Labels name="entity" toName="poem"><Label value="entity"/></Labels>'
        '<Header value="Атрибуты выделенного региона"/>'
        + region_choices("source_domain", DOMAINS, False)
        + region_choices("target_domain", DOMAINS, False)
        + region_choices("sentiment", SENTIMENTS, False)
        + '<TextArea name="semantic_label" toName="poem" perRegion="true" maxSubmissions="1" '
        'visibleWhen="region-selected" placeholder="Семантическая метка, напр. благородный муж"/>'
        + region_choices("entity_type", ENTITY_TYPES, False)
        + region_choices("usage_type", USAGE_TYPES, False)
        + "</View>\n"
    )
    target = ROOT / "annotation/label_studio.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(xml, encoding="utf-8")


if __name__ == "__main__":
    main()
