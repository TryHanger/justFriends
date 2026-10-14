"""Backend integration boundary. Heavy models load once on first request."""

from functools import lru_cache

from app.core.config import get_settings
from app.nlp.contracts import NLPInputError, output_schema
from app.nlp.pipeline import build_pipeline
from app.schemas.analysis import AnalysisResult

OUTPUT_SCHEMA = output_schema()


class AnalyzerNotConfigured(Exception):
    pass


class AnalyzerOutputInvalid(Exception):
    pass


class AnalyzerInputInvalid(Exception):
    pass


@lru_cache(maxsize=2)
def get_pipeline(model_profile: str = "default"):
    try:
        settings = get_settings()
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
        result = pipeline.analyze(text, language)
        if model_profile == "experimental_kk":
            return result.model_copy(
                update={
                    "model_version": "xlmr-kk-silver-pilot-v2",
                    "needs_review": True,
                    "warnings": [
                        *result.warnings,
                        "Экспериментальная казахская модель: Silver-пилот, не Gold-оценка.",
                    ],
                    "method": {
                        **result.method,
                        "model_profile": "experimental_kk",
                        "supervision": "silver-pilot",
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
    except NLPInputError as exc:
        raise AnalyzerInputInvalid(str(exc)) from exc
    except ValueError as exc:
        raise AnalyzerOutputInvalid(str(exc)) from exc
