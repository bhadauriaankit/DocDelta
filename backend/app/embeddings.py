"""
Pluggable "embedding" providers for semantic paragraph matching.

Real sentence-transformer embeddings need a real model — sentence-
transformers as a package pulls in PyTorch, and a plain `pip install
sentence-transformers` installs the full CUDA/GPU build of PyTorch by
default. Confirmed while building this: it started downloading several
GB of nvidia-* wheels before even reaching the actual model download
step, on a machine with no GPU to use any of them. That's a genuinely
bad default for a local learning project running in Docker Desktop —
multi-gigabyte image bloat and slow builds, for a dependency most people
running this project don't need on day one.

So: sentence-transformers is an OPTIONAL, disabled-by-default upgrade —
see requirements-semantic.txt for how to install it properly (CPU-only
PyTorch wheel, much smaller). The default provider here is TF-IDF +
cosine similarity (scikit-learn): fully local, no downloads, no GPU
dependency, genuinely useful — but it's lexical (word-overlap)
similarity, not true meaning-based similarity. A pure paraphrase that
shares no words with the original ("the deadline is Friday" vs "must be
done by end of week") will NOT score as similar under TF-IDF the way it
would with real embeddings. That's a real, stated limitation, not a
detail to gloss over — see the module docstring in semantic_diff.py for
how this shapes what Phase 7 can actually promise.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    name: str

    @abstractmethod
    def similarity_matrix(self, original_texts: list[str], modified_texts: list[str]) -> np.ndarray:
        """Returns an (len(original_texts) x len(modified_texts)) matrix
        of similarity scores. Cosine similarity can technically go
        slightly negative for some embeddings — callers should clip to
        [0, 1] rather than assume this method already did."""


class TfidfSimilarity(EmbeddingProvider):
    name = "tfidf"

    def similarity_matrix(self, original_texts: list[str], modified_texts: list[str]) -> np.ndarray:
        if not original_texts or not modified_texts:
            return np.zeros((len(original_texts), len(modified_texts)))

        # TF-IDF needs a shared vocabulary to compare vectors against —
        # fit on both sides together, then split the resulting matrix
        # back into "original rows" and "modified rows".
        vectorizer = TfidfVectorizer()
        try:
            combined_matrix = vectorizer.fit_transform([*original_texts, *modified_texts])
        except ValueError:
            # Every paragraph on both sides was empty or pure stopwords
            # after tokenization — nothing meaningful to vectorize.
            return np.zeros((len(original_texts), len(modified_texts)))

        original_vectors = combined_matrix[: len(original_texts)]
        modified_vectors = combined_matrix[len(original_texts) :]
        return cosine_similarity(original_vectors, modified_vectors)


class SentenceTransformerSimilarity(EmbeddingProvider):
    """Real semantic embeddings. OPTIONAL — requires the dependency in
    requirements-semantic.txt (installed separately, see that file for
    why) plus a one-time ~90MB model download from Hugging Face on first
    use. Never imported unless SEMANTIC_PROVIDER=sentence-transformers is
    explicitly set."""

    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # optional dependency, imported lazily on purpose

        self._model = SentenceTransformer(model_name)

    def similarity_matrix(self, original_texts: list[str], modified_texts: list[str]) -> np.ndarray:
        if not original_texts or not modified_texts:
            return np.zeros((len(original_texts), len(modified_texts)))
        original_embeddings = self._model.encode(original_texts, normalize_embeddings=True)
        modified_embeddings = self._model.encode(modified_texts, normalize_embeddings=True)
        return cosine_similarity(original_embeddings, modified_embeddings)


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Picks a provider once per process and caches it — constructing
    SentenceTransformerSimilarity loads a real model into memory, which
    is far too expensive to redo per request.

    Only attempts sentence-transformers if explicitly configured to. If
    that import or model load fails for any reason (package not
    installed, no internet for the first-time model download, corrupted
    cache), falls back to TF-IDF and logs exactly why — this comparison
    should degrade gracefully, not take the whole job down, if the
    optional ML dependency isn't available.
    """
    global _provider
    if _provider is not None:
        return _provider

    if settings.SEMANTIC_PROVIDER == "sentence-transformers":
        try:
            _provider = SentenceTransformerSimilarity()
            return _provider
        except Exception:
            logger.warning(
                "SEMANTIC_PROVIDER=sentence-transformers but the model could not be "
                "loaded (package not installed, or no internet access for the "
                "first-time download) — falling back to TF-IDF similarity instead.",
                exc_info=True,
            )

    _provider = TfidfSimilarity()
    return _provider
