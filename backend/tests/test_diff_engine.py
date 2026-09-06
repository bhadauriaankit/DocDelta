from app.diff_engine import compare_text


def test_identical_text_is_100_percent_similar():
    result = compare_text("hello world", "hello world")
    assert result.similarity == 1.0
    assert result.stats["added"] == 0
    assert result.stats["removed"] == 0
    assert result.stats["replaced"] == 0


def test_detects_a_replaced_word():
    result = compare_text(
        "The project deadline is 30 August 2026.",
        "The project deadline is 15 September 2026.",
    )
    assert result.stats["replaced"] >= 1
    assert result.similarity < 1.0


def test_detects_pure_addition():
    result = compare_text("Hello", "Hello world")
    assert result.stats["added"] == 1
    assert result.stats["removed"] == 0


def test_detects_pure_removal():
    result = compare_text("Hello world", "Hello")
    assert result.stats["removed"] == 1
    assert result.stats["added"] == 0


def test_completely_different_text_has_low_similarity():
    result = compare_text("apples oranges bananas", "quantum physics rocket science")
    # Note: not near-zero even for unrelated text — matching whitespace
    # tokens between words pulls the ratio up a bit. That's expected
    # behavior of difflib's ratio(), not a bug.
    assert result.similarity < 0.4
