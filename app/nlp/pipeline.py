"""Public NLP entry point independent of HTTP, files, and the database."""

from app.nlp.contracts import NLPInputError, validate_result


class MetaphorPipeline:
    def __init__(self, detector, classifier=None):
        self.detector, self.classifier = detector, classifier

    def analyze(self, text: str, language: str = "auto"):
        if not text.strip() or len(text) > 100000:
            raise NLPInputError("Text must contain 1..100000 characters and not be whitespace only")
        result = self.detector.analyze(text, language)
        if self.classifier:
            result = self.classifier.classify(text, result)
        return validate_result(text, language, result)


def build_pipeline(settings):
    from app.nlp.baseline import LexicalDetector
    from app.nlp.llm import OllamaDetector, OpenAIDetector

    def llm(provider):
        if provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required for the OpenAI backend")
            return OpenAIDetector(settings.openai_model, settings.openai_api_key)
        return OllamaDetector(
            settings.ollama_model,
            settings.ollama_base_url,
            context_window=settings.ollama_context_window,
        )

    backend = settings.nlp_backend
    if backend == "baseline":
        detector = LexicalDetector()
    elif backend in {"openai", "ollama"}:
        detector = llm(backend)
    else:
        from app.nlp.xlmr import XLMRDetector

        detector = XLMRDetector(
            settings.xlmr_model_path, settings.nlp_max_length, settings.nlp_stride
        )
        if backend == "hybrid":
            from app.nlp.hybrid import HybridDetector

            detector = HybridDetector(
                detector, llm(settings.hybrid_llm_backend), settings.nlp_review_threshold
            )
    classifier = None
    if settings.attribute_model_path:
        if backend != "xlmr":
            raise ValueError("ATTRIBUTE_MODEL_PATH is only used with NLP_BACKEND=xlmr")
        from app.nlp.attributes import AttributeClassifier

        classifier = AttributeClassifier(settings.attribute_model_path)
    return MetaphorPipeline(detector, classifier)
