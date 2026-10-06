"""Versioned vocabulary shared by annotation, models and the API."""

from typing import Literal, get_args

# 2.0: entity candidates, literal/metaphorical usage, semantic labels and sentiment (ТЗ п. 4.1).
TAXONOMY_VERSION = "2.0"
MetaphorLabel = Literal["metaphor", "simile", "personification", "metonymy", "idiom"]
Domain = Literal[
    "nature",
    "water",
    "fire",
    "light",
    "darkness",
    "plant",
    "animal",
    "body",
    "person",
    "object",
    "space",
    "motion",
    "journey",
    "time",
    "life",
    "death",
    "emotion",
    "love",
    "mind",
    "society",
    "spirituality",
    "other",
    "unknown",
]
# Type of the concrete or abstract entity that carries (or could carry) a figurative meaning.
EntityType = Literal[
    "plant",
    "animal",
    "natural_phenomenon",
    "landscape",
    "celestial",
    "body",
    "person",
    "artifact",
    "abstract",
    "other",
]
UsageType = Literal["metaphorical", "literal"]
Sentiment = Literal["positive", "neutral", "negative"]

LABELS = get_args(MetaphorLabel)
DOMAINS = get_args(Domain)
ENTITY_TYPES = get_args(EntityType)
USAGE_TYPES = get_args(UsageType)
SENTIMENTS = get_args(Sentiment)
# Simile, metonymy and idiom are auxiliary figures, not automatic positive examples.
METAPHOR_LABELS = frozenset({"metaphor", "personification"})
BIO_LABELS = ("O", "B-METAPHOR", "I-METAPHOR")
