"""Public NLP entry point independent of HTTP, files, and the database."""

from app.core.limits import MAX_ANALYSIS_CHARS
from app.nlp.contracts import NLPInputError, context_sentence, validate_result


class MetaphorPipeline:
    """Modules A-D in order; module E (expert review) works on the stored result."""

    def __init__(self, detector, classifier=None, extractor=None, calibrator=None):
        self.detector, self.classifier, self.extractor = detector, classifier, extractor
        self.calibrator = calibrator

    def analyze(self, text: str, language: str = "auto"):
        if not text.strip() or len(text) > MAX_ANALYSIS_CHARS:
            raise NLPInputError("Text must contain 1..100000 characters and not be whitespace only")
        result = self.detector.analyze(text, language)
        if self.classifier:
            result = self.classifier.classify(text, result)
        update = {
            "metaphors": [
                span
                if span.context_sentence
                else span.model_copy(
                    update={"context_sentence": context_sentence(text, span.start, span.end)}
                )
                for span in result.metaphors
            ]
        }
        if self.extractor and not result.candidates:
            # Detectors without module B (XLM-R) still expose soft-lexicon candidates.
            update["candidates"] = self.extractor.extract(text, result.language)
        result = result.model_copy(update=update)
        if self.calibrator:
            result = self.calibrator.apply(result)
        return validate_result(text, language, result)


LLM_BACKENDS = {"openai", "anthropic", "ollama", "hf"}


def two_stage_languages(settings) -> frozenset[str]:
    languages = frozenset(
        part.strip() for part in settings.nlp_two_stage_languages.split(",") if part.strip()
    )
    if languages - {"zh", "kk"}:
        raise ValueError("NLP_TWO_STAGE_LANGUAGES must list zh and/or kk")
    return languages


def build_llm(settings, provider: str, strategy: str | None = None):
    from app.nlp.lexicon import CandidateExtractor

    common = dict(
        strategy=strategy or settings.llm_prompt_strategy,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        extractor=CandidateExtractor(settings.lexicon_dir),
        rag_k=settings.rag_top_k,
    )
    if settings.knowledge_dir:
        from app.nlp.rag import default_knowledge

        common["knowledge"] = default_knowledge(settings.knowledge_dir)
    languages = two_stage_languages(settings)
    if languages:
        from app.nlp.usage import UsageJudge

        # Only the provider call of this detector is used; temperature 0 is set per request.
        judge = _llm(
            settings,
            settings.nlp_usage_backend,
            dict(strategy="zero_shot", temperature=0.0, top_p=None),
            settings.nlp_usage_model,
        )
        common["usage_judge"] = UsageJudge(judge, languages)
    return _llm(settings, provider, common)


def _llm(settings, provider: str, common: dict, model: str | None = None):
    from app.nlp.llm import OllamaDetector, OpenAIDetector

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for the OpenAI backend"
                + (
                    " of the two-stage usage judge; set NLP_USAGE_BACKEND or disable it "
                    "with an empty NLP_TWO_STAGE_LANGUAGES"
                    if model
                    else ""
                )
            )
        return OpenAIDetector(model or settings.openai_model, settings.openai_api_key, **common)
    if provider == "anthropic":
        from app.nlp.claude import ClaudeDetector

        return ClaudeDetector(
            model or settings.anthropic_model,
            settings.anthropic_api_key,
            effort=settings.anthropic_effort,
            **common,
        )
    if provider == "hf":
        if not settings.hf_model:
            raise ValueError("HF_MODEL is required for the hf backend")
        from app.nlp.hf_local import TransformersDetector

        return TransformersDetector(settings.hf_model, settings.hf_adapter, **common)
    if provider == "ollama":
        return OllamaDetector(
            model or settings.ollama_model,
            settings.ollama_base_url,
            context_window=settings.ollama_context_window,
            **common,
        )
    raise ValueError(f"Unknown LLM provider {provider}")


def build_pipeline(settings, strategy: str | None = None):
    from app.nlp.baseline import LexicalDetector

    backend = settings.nlp_backend
    if backend == "baseline":
        detector = LexicalDetector(settings.lexicon_dir)
    elif backend in LLM_BACKENDS:
        detector = build_llm(settings, backend, strategy)
    else:
        from app.nlp.xlmr import XLMRDetector

        detector = XLMRDetector(
            settings.xlmr_model_path, settings.nlp_max_length, settings.nlp_stride
        )
        if backend == "hybrid":
            from app.nlp.hybrid import HybridDetector

            detector = HybridDetector(
                detector,
                build_llm(settings, settings.hybrid_llm_backend, strategy),
                settings.nlp_review_threshold,
            )
    classifier = None
    if settings.attribute_model_path:
        if backend != "xlmr":
            raise ValueError("ATTRIBUTE_MODEL_PATH is only used with NLP_BACKEND=xlmr")
        from app.nlp.attributes import AttributeClassifier

        classifier = AttributeClassifier(settings.attribute_model_path)
    from app.nlp.calibration import Calibrator
    from app.nlp.lexicon import CandidateExtractor

    return MetaphorPipeline(
        detector,
        classifier,
        CandidateExtractor(settings.lexicon_dir),
        Calibrator.load(settings.nlp_review_threshold),
    )
