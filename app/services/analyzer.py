"""Backend integration boundary. Heavy models load once on first request."""

from functools import lru_cache

from app.core.config import get_settings
from app.nlp.contracts import NLPInputError, output_schema
from app.nlp.llm import INSTRUCTIONS  # noqa: F401
from app.nlp.pipeline import build_pipeline
from app.schemas.analysis import AnalysisResult

OUTPUT_SCHEMA = output_schema()


class AnalyzerNotConfigured(Exception):
    pass


class AnalyzerOutputInvalid(Exception):
    pass


class AnalyzerInputInvalid(Exception):
    pass


@lru_cache(maxsize=1)
def get_pipeline():
    try:
        return build_pipeline(get_settings())
    except (ValueError, ImportError, OSError) as exc:
        raise AnalyzerNotConfigured(str(exc)) from exc


def analyze_text(text: str, language: str) -> AnalysisResult:
    pipeline = get_pipeline()
    try:
        return pipeline.analyze(text, language)
    except NLPInputError as exc:
        raise AnalyzerInputInvalid(str(exc)) from exc
    except ValueError as exc:
        raise AnalyzerOutputInvalid(str(exc)) from exc
