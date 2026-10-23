"""Backend integration boundary. Heavy models load once on first request."""

from functools import lru_cache

from app.core.config import get_settings
from app.nlp.contracts import NLPInputError, output_schema
from app.nlp.pipeline import LLM_BACKENDS, build_pipeline
from app.nlp.unified import UnifiedPipeline
from app.nlp.xlmr import checkpoint_ready
from app.schemas.analysis import AnalysisResult

OUTPUT_SCHEMA = output_schema()
# XLM-R profile used by the unified profile for each language, with its checkpoint setting.
XLMR_PROFILES = {
    "zh": ("xlmr_zh_gold_v2", "chinese_gold_xlmr_model_path"),
    "kk": ("experimental_kk", "experimental_kk_xlmr_model_path"),
}


class AnalyzerNotConfigured(Exception):
    pass


class AnalyzerOutputInvalid(Exception):
    pass


class AnalyzerInputInvalid(Exception):
    pass


def _xlmr_for(language: str):
    """Calibrated XLM-R analysis of `language` for the unified profile; None when its
    weights or PyTorch are absent. The checkpoint loads on first use and stays cached."""
    profile, path = XLMR_PROFILES[language]
    if not checkpoint_ready(getattr(get_settings(), path)):
        return None
    return lambda text: _profiled(get_pipeline(profile).analyze(text, language), profile)


# One entry per profile: the unified profile reuses the default and XLM-R pipelines.
@lru_cache(maxsize=8)
def get_pipeline(model_profile: str = "default"):
    try:
        settings = get_settings()
        if model_profile == "unified":
            if settings.nlp_backend not in LLM_BACKENDS:
                raise ValueError("The unified profile needs an LLM NLP_BACKEND")
            return UnifiedPipeline(
                get_pipeline("default"), _xlmr_for, settings.nlp_review_threshold
            )
        if model_profile == "experimental_kk":
            settings = settings.model_copy(
                update={
                    "nlp_backend": "xlmr",
                    "xlmr_model_path": settings.experimental_kk_xlmr_model_path,
                }
            )
        elif model_profile == "xlmr_zh_gold_v2":
            settings = settings.model_copy(
                update={"nlp_backend": "xlmr", "xlmr_model_path": settings.chinese_gold_xlmr_model_path}
            )
        elif model_profile == "baseline":
            settings = settings.model_copy(update={"nlp_backend": "baseline"})
        elif model_profile != "default":
            raise ValueError(f"Unknown model profile: {model_profile}")
        return build_pipeline(settings)
    except (ValueError, ImportError, OSError) as exc:
        raise AnalyzerNotConfigured(str(exc)) from exc


def analyze_text(text: str, language: str, model_profile: str = "default") -> AnalysisResult:
    restricted_languages = {"experimental_kk": "kk", "xlmr_zh_gold_v2": "zh"}
    if model_profile in restricted_languages and language != restricted_languages[model_profile]:
        raise AnalyzerInputInvalid(
            f"Selected model requires language={restricted_languages[model_profile]}"
        )
    pipeline = get_pipeline(model_profile)
    try:
        return _profiled(pipeline.analyze(text, language), model_profile)
    except NLPInputError as exc:
        raise AnalyzerInputInvalid(str(exc)) from exc
    except ValueError as exc:
        raise AnalyzerOutputInvalid(str(exc)) from exc


def _profiled(result: AnalysisResult, model_profile: str) -> AnalysisResult:
    """Model version, provenance and caveats of the fine-tuned XLM-R profiles."""
    if model_profile == "experimental_kk":
        return result.model_copy(
            update={
                "model_version": "xlmr-kk-expert-v2",
                "needs_review": True,
                "warnings": [
                    *result.warnings,
                    "Казахская XLM-R дообучена на словарных цитатах и silver-разметке; согласие со словарём κ 0.20 — используйте как подсказку.",
                ],
                "method": {
                    **result.method,
                    "model_profile": "experimental_kk",
                    "supervision": "expert-dictionary+silver",
                },
            }
        )
    if model_profile == "xlmr_zh_gold_v2":
        return result.model_copy(
            update={
                "model_version": "xlmr-zh-gold-v2",
                "method": {**result.method, "model_profile": "xlmr_zh_gold_v2", "supervision": "gold"},
            }
        )
    return result
