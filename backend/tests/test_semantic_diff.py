from app.semantic_diff import compare_semantic


def test_identical_paragraphs_are_exact_matches():
    text = "First paragraph.\n\nSecond paragraph."
    result = compare_semantic(text, text)

    assert result.stats["exact_match"] == 2
    assert all(m.type == "exact_match" for m in result.matches)
    assert all(m.confidence is None for m in result.matches)  # deterministic, no model judgment involved


def test_reworded_paragraph_is_not_an_exact_match_but_is_matched():
    original = "The employee must submit the report before Friday."
    modified = "The report must be submitted before Friday by the employee."

    result = compare_semantic(original, modified)

    assert result.stats["exact_match"] == 0
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.type != "exact_match"
    # Not "minor_wording_change" or higher: TF-IDF has no stemming, so
    # "submit" vs "submitted" count as entirely different tokens, which
    # pulls real word-overlap sentences like this one down to
    # "meaningful_change" territory rather than scoring them as near-
    # identical. This is exactly the kind of case real embeddings would
    # score higher — documented as a known limitation, not silently
    # smoothed over in this test.
    assert match.type in ("minor_wording_change", "semantically_similar", "meaningful_change")
    assert match.original == original
    assert match.modified == modified
    assert match.confidence in ("high", "low")


def test_completely_unrelated_paragraphs_score_as_major_change_not_added_removed():
    """One paragraph on each side, totally unrelated — there's nothing
    else to match against, so the algorithm still pairs them (rather than
    calling one 'removed' and the other 'added'), just with a low
    similarity score and the 'major_change' tier."""
    original = "Quarterly revenue increased by twelve percent."
    modified = "Please remember to water the office plants."

    result = compare_semantic(original, modified)
    assert len(result.matches) == 1
    assert result.matches[0].type == "major_change"


def test_added_paragraph_with_no_original_counterpart():
    original = "Paragraph one."
    modified = "Paragraph one.\n\nThis is a brand new paragraph."

    result = compare_semantic(original, modified)
    assert result.stats["exact_match"] == 1
    assert result.stats["added"] == 1
    added = [m for m in result.matches if m.type == "added"][0]
    assert added.modified == "This is a brand new paragraph."
    assert added.original is None


def test_removed_paragraph_with_no_modified_counterpart():
    original = "Paragraph one.\n\nThis paragraph gets deleted."
    modified = "Paragraph one."

    result = compare_semantic(original, modified)
    assert result.stats["exact_match"] == 1
    assert result.stats["removed"] == 1


def test_matching_by_similarity_not_position():
    """Paragraph order swapped — a positional (index-based) comparison
    would call both paragraphs completely different. Similarity-based
    matching should still recognize each as an exact match to its
    counterpart, just at a different position."""
    original = "Alpha paragraph.\n\nBeta paragraph."
    modified = "Beta paragraph.\n\nAlpha paragraph."

    result = compare_semantic(original, modified)
    assert result.stats["exact_match"] == 2


def test_falls_back_to_line_splitting_for_flattened_spreadsheet_text():
    """Phase 5's flattened spreadsheet text has no blank-line paragraph
    breaks — just one line per row. This should still split into multiple
    comparable units instead of being treated as one giant paragraph."""
    original = "Sheet1: Name | Salary\nSheet1: Alice | 45000"
    modified = "Sheet1: Name | Salary\nSheet1: Alice | 52000"

    result = compare_semantic(original, modified)
    assert len(result.matches) == 2
    assert result.stats["exact_match"] == 1  # header row unchanged


def test_empty_documents_produce_no_matches():
    result = compare_semantic("", "")
    assert result.matches == []
    assert result.stats["exact_match"] == 0


def test_one_sided_empty_document_produces_only_additions():
    result = compare_semantic("", "New content that didn't exist before.")
    assert result.stats["added"] == 1
    assert result.stats["exact_match"] == 0
