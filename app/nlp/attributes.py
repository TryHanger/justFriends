"""Character TF-IDF baselines for figure type and semantic domains."""

from pathlib import Path
import json

from app.nlp.corpus import manifest, require_gold, save_json
from app.schemas.analysis import AnalysisResult

FIELDS = ("label", "source_domain", "target_domain")


def context(text, span, language):
    return (
        f"{language} {span.text} [CONTEXT] "
        f"{text[max(0, span.start - 100) : min(len(text), span.end + 100)]}"
    )


def train_attributes(records, output_dir, allow_synthetic=False):
    import joblib
    import sklearn
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    require_gold(records, allow_synthetic)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty")
    pairs = [(record, span) for record in records for span in record.spans]
    if not pairs:
        raise ValueError("Attribute training requires labeled spans")
    texts = [context(r.text, s, r.language) for r, s in pairs]
    models = {}
    for field in FIELDS:
        labels = [getattr(s, field) for _, s in pairs]
        usable = [(x, y) for x, y in zip(texts, labels) if y != "unknown"]
        if len({y for _, y in usable}) < 2:
            raise ValueError(f"Need at least two known classes for {field}")
        model = make_pipeline(
            TfidfVectorizer(
                analyzer="char", ngram_range=(1, 4), max_features=50000, sublinear_tf=True
            ),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
        )
        model.fit([x for x, _ in usable], [y for _, y in usable])
        models[field] = model
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, output / "attributes.joblib")
    save_json(
        output / "experiment.json",
        {
            "kind": "char-tfidf-logistic-regression",
            "model_version": "attributes-v1-" + manifest(records)["sha256"][:12],
            "scikit_learn": sklearn.__version__,
            "train": manifest(records),
            "synthetic_smoke_test": allow_synthetic,
        },
    )


class AttributeClassifier:
    def __init__(self, model_path):
        import joblib

        # Only load artifacts trained by this project: joblib uses Python pickle.
        self.models = joblib.load(Path(model_path) / "attributes.joblib")
        metadata = json.loads((Path(model_path) / "experiment.json").read_text(encoding="utf-8"))
        self.version = metadata["model_version"]

    def classify(self, text: str, result: AnalysisResult) -> AnalysisResult:
        spans = []
        for span in result.metaphors:
            features = [context(text, span, result.language)]
            values, confidence = {}, span.confidence
            for field in FIELDS:
                model = self.models[field]
                probabilities = model.predict_proba(features)[0]
                index = probabilities.argmax()
                values[field] = str(model.classes_[index])
                confidence = min(confidence, float(probabilities[index]))
            spans.append(
                span.model_copy(
                    update={
                        **values,
                        "confidence": confidence,
                        "rationale": span.rationale + " Attributes predicted by TF-IDF classifier.",
                    }
                )
            )
        return result.model_copy(
            update={
                "metaphors": spans,
                "model_version": result.model_version + "+" + self.version,
                "warnings": ["Detection and attribute scores are uncalibrated."],
                "needs_review": True,
            }
        )
