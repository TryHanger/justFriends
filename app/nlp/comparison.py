"""Symmetric multilingual-e5 similarity; cosine is not cultural equivalence."""

from app.schemas.comparison import ComparisonItem, ComparisonMatch, ComparisonResult


class CrossLanguageMatcher:
    def __init__(self, model_name="intfloat/multilingual-e5-base", encoder=None, device=None):
        if encoder is None:
            from sentence_transformers import SentenceTransformer

            encoder = SentenceTransformer(model_name, device=device)
        self.encoder, self.model_name = encoder, model_name

    def compare(
        self, queries: list[ComparisonItem], candidates: list[ComparisonItem], k: int = 5
    ) -> ComparisonResult:
        import numpy as np

        if k < 1 or not queries or not candidates:
            raise ValueError("Nonempty queries/candidates and positive k required")
        for items in (queries, candidates):
            if len({item.id for item in items}) != len(items):
                raise ValueError("IDs must be unique within each collection")
        items = queries + candidates
        # E5 recommends query: on both sides of symmetric semantic similarity.
        texts = ["query: " + x.text + ("\n" + x.context if x.context else "") for x in items]
        tokenizer = getattr(self.encoder, "tokenizer", None)
        if tokenizer is not None:
            lengths = [len(tokenizer(t, truncation=False)["input_ids"]) for t in texts]
            if max(lengths) > self.encoder.max_seq_length:
                raise ValueError("Embedding context is too long; shorten it explicitly")
        vectors = np.asarray(
            self.encoder.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        )
        if vectors.ndim != 2 or len(vectors) != len(items) or not np.isfinite(vectors).all():
            raise ValueError("Invalid embeddings")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if (norms == 0).any():
            raise ValueError("Zero-length embedding")
        vectors = vectors / norms
        similarities = vectors[: len(queries)] @ vectors[len(queries) :].T
        matches = []
        for i, query in enumerate(queries):
            eligible = [
                j
                for j, item in enumerate(candidates)
                if item.language != query.language and item.id != query.id
            ]
            ranked = sorted(eligible, key=lambda j: (-float(similarities[i, j]), candidates[j].id))
            for rank, j in enumerate(ranked[:k], 1):
                matches.append(
                    ComparisonMatch(
                        query_id=query.id,
                        candidate_id=candidates[j].id,
                        similarity=float(similarities[i, j].clip(-1, 1)),
                        rank=rank,
                    )
                )
        return ComparisonResult(
            model_version=self.model_name,
            matches=matches,
            warnings=[
                "Similarity ranks semantic candidates; it does not prove "
                "a shared metaphor or cultural equivalence."
            ],
        )
