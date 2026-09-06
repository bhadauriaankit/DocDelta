import numpy as np
import pytest

from app.embeddings import TfidfSimilarity


def test_tfidf_identical_texts_score_high():
    provider = TfidfSimilarity()
    matrix = provider.similarity_matrix(["the quick brown fox"], ["the quick brown fox"])
    assert matrix[0][0] == pytest.approx(1.0, abs=0.01)


def test_tfidf_shared_vocabulary_scores_moderately_high():
    provider = TfidfSimilarity()
    matrix = provider.similarity_matrix(
        ["The employee must submit the report before Friday."],
        ["The report must be submitted before Friday by the employee."],
    )
    assert matrix[0][0] > 0.7  # heavy word overlap, just reordered


def test_tfidf_completely_different_texts_score_low():
    provider = TfidfSimilarity()
    matrix = provider.similarity_matrix(
        ["The quarterly revenue report is attached."],
        ["Please water the office plants on Fridays."],
    )
    assert matrix[0][0] < 0.2


def test_tfidf_known_limitation_pure_paraphrase_scores_low():
    """Documents the real, stated limitation: TF-IDF is lexical, not
    semantic. A paraphrase sharing almost no words with the original will
    NOT score as similar, even though a human (or real embeddings) would
    recognize these as saying almost the same thing. This test exists to
    make sure that limitation stays visible and honest, not to celebrate
    it — if TF-IDF ever get replaced with something that DOES catch this,
    this test should be revisited, not just deleted."""
    provider = TfidfSimilarity()
    matrix = provider.similarity_matrix(
        ["The deadline is this Friday."],
        ["It must be completed by the end of the week."],
    )
    assert matrix[0][0] < 0.3


def test_tfidf_handles_empty_input_lists():
    provider = TfidfSimilarity()
    assert provider.similarity_matrix([], ["something"]).shape == (0, 1)
    assert provider.similarity_matrix(["something"], []).shape == (1, 0)
    assert provider.similarity_matrix([], []).shape == (0, 0)


def test_tfidf_handles_empty_strings_without_crashing():
    provider = TfidfSimilarity()
    matrix = provider.similarity_matrix([""], [""])
    assert matrix.shape == (1, 1)
    assert not np.isnan(matrix[0][0])


def test_get_embedding_provider_defaults_to_tfidf(monkeypatch):
    import app.embeddings as embeddings_module

    monkeypatch.setattr(embeddings_module, "_provider", None)
    provider = embeddings_module.get_embedding_provider()
    assert provider.name == "tfidf"


def test_get_embedding_provider_falls_back_when_sentence_transformers_unavailable(monkeypatch):
    """sentence-transformers is deliberately NOT in requirements.txt (see
    embeddings.py's docstring for why) — so requesting it should fail the
    import and fall back to tfidf, not crash the whole comparison. This
    is a genuine test of the fallback path, not a mock: the import really
    does fail in this environment, exactly as it would for anyone who
    hasn't installed the optional dependency."""
    import app.embeddings as embeddings_module

    monkeypatch.setattr(embeddings_module, "_provider", None)
    monkeypatch.setattr(embeddings_module.settings, "SEMANTIC_PROVIDER", "sentence-transformers")

    provider = embeddings_module.get_embedding_provider()
    assert provider.name == "tfidf"
