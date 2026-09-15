"""Regenerate versioned integration artifacts: python -m scripts.export_nlp_contracts."""

from pathlib import Path
from xml.sax.saxutils import escape

from app.nlp.contracts import output_schema
from app.nlp.corpus import Poem, save_json
from app.schemas.analysis import AnalysisResult
from app.schemas.comparison import ComparisonItem, ComparisonResult
from app.schemas.taxonomy import DOMAINS, LABELS, METAPHOR_LABELS, TAXONOMY_VERSION

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name, schema in {
        "llm-output": output_schema(),
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
            "bio_positive_labels": sorted(METAPHOR_LABELS),
            "offset_unit": "unicode_codepoint",
            "end_exclusive": True,
        },
    )
    labels = "".join(f'<Label value="{escape(x)}"/>' for x in LABELS)
    choices = "".join(f'<Choice value="{escape(x)}"/>' for x in DOMAINS)
    xml = (
        f'<View><Text name="poem" value="$text"/>'
        f'<Labels name="figure" toName="poem">{labels}</Labels>'
        f'<Choices name="source_domain" toName="poem" perRegion="true" '
        f'choice="single" required="true">{choices}</Choices>'
        f'<Choices name="target_domain" toName="poem" perRegion="true" '
        f'choice="single" required="true">{choices}</Choices></View>\n'
    )
    target = ROOT / "annotation/label_studio.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(xml, encoding="utf-8")


if __name__ == "__main__":
    main()
