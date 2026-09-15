"""Versioned vocabulary shared by annotation, models and the API."""

from typing import Literal, get_args

TAXONOMY_VERSION = "1.0"
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
LABELS = get_args(MetaphorLabel)
DOMAINS = get_args(Domain)
# Simile, metonymy and idiom are auxiliary figures, not automatic positive examples.
METAPHOR_LABELS = frozenset({"metaphor", "personification"})
BIO_LABELS = ("O", "B-METAPHOR", "I-METAPHOR")
