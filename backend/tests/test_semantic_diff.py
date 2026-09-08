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


def test_paragraph_match_includes_word_level_segments():
    original = (
        "Clause 1: The agreement is effective immediately.\n\n"
        "Clause 2: Payment is due within 30 days."
    )
    modified = (
        "Clause 1: The agreement is effective immediately.\n\n"
        "Clause 2: Payment is due within 15 days.\n\n"
        "Clause 3: Brand new added section."
    )

    result = compare_semantic(original, modified)

    # 1 exact match (Clause 1), 1 wording change (Clause 2), 1 added (Clause 3)
    exact_matches = [m for m in result.matches if m.type == "exact_match"]
    assert len(exact_matches) == 1
    assert len(exact_matches[0].segments) >= 1
    assert all(s.type == "equal" for s in exact_matches[0].segments)

    changed_matches = [m for m in result.matches if m.type in ("minor_wording_change", "semantically_similar", "meaningful_change", "major_change")]
    assert len(changed_matches) == 1
    c2 = changed_matches[0]
    assert "Payment is due" in (c2.original or "")
    changed_types = [s.type for s in c2.segments]
    assert "equal" in changed_types
    assert "replaced" in changed_types

    added_matches = [m for m in result.matches if m.type == "added"]
    assert len(added_matches) == 1
    assert all(s.type == "added" for s in added_matches[0].segments)

    # Test removed paragraph
    res_removed = compare_semantic(
        "Clause 1: Same.\n\nClause 2: Removed paragraph.",
        "Clause 1: Same."
    )
    removed_matches = [m for m in res_removed.matches if m.type == "removed"]
    assert len(removed_matches) == 1
    assert all(s.type == "removed" for s in removed_matches[0].segments)


def test_matches_preserve_document_order():
    """Confirms that reworded or added paragraphs are not lumped at the end,
    but follow the natural document flow."""
    original = (
        "Clause 1: First clause text.\n\n"
        "Clause 2: Second clause with 30 days deadline.\n\n"
        "Clause 3: Third clause text."
    )
    modified = (
        "Clause 1: First clause text.\n\n"
        "Clause 2: Second clause with 14 days deadline.\n\n"
        "Clause 3: Third clause text."
    )

    result = compare_semantic(original, modified)
    assert len(result.matches) == 3
    assert result.matches[0].type == "exact_match"
    assert "Clause 1" in (result.matches[0].original or "")

    assert result.matches[1].type != "exact_match"
    assert "Clause 2" in (result.matches[1].original or "")

    assert result.matches[2].type == "exact_match"
    assert "Clause 3" in (result.matches[2].original or "")


def test_long_document_performance_and_scaling():
    """100+ paragraphs with mixed exact matches and wording changes to confirm
    per-row compare_text remains fast and produces segments for each row."""
    import time

    original_paragraphs = [
        f"Section {i}: This is standard clause boilerplate with term {i * 10}."
        for i in range(120)
    ]
    modified_paragraphs = list(original_paragraphs)
    # Modify every 5th paragraph
    for i in range(0, 120, 5):
        modified_paragraphs[i] = (
            f"Section {i}: This is updated clause terms with revised duration {i * 12}."
        )

    t0 = time.perf_counter()
    result = compare_semantic(
        "\n\n".join(original_paragraphs),
        "\n\n".join(modified_paragraphs),
    )
    elapsed = time.perf_counter() - t0

    assert len(result.matches) == 120
    assert elapsed < 2.0  # well under 2 seconds for 120 paragraphs
    assert all(len(m.segments) > 0 for m in result.matches)


