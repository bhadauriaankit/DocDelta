"""
Paragraph-level semantic comparison — Phase 7.

Splits each document's flattened text into paragraphs, matches original
paragraphs to modified paragraphs by similarity (not position — a
paragraph that moved should still be recognized as "the same paragraph,
maybe reworded," not compared against whatever happens to sit at the same
index), and classifies each matched pair into a tier: exact match, minor
wording change, semantically similar, meaningful change, major change.
Unmatched paragraphs come back as added/removed — same vocabulary as
table_diff.py and visual_diff.py use for their own unmatched rows/pages.

Two deliberate design choices worth stating plainly:

1. Exact matches are found BEFORE any similarity model runs at all. This
   isn't just a speed optimization — an unchanged paragraph should never
   be at the mercy of a similarity model's approximation. Per the
   project's "use AI only where it adds real value" principle, a
   deterministic string comparison is strictly more trustworthy than a
   model's opinion for the one case where it's actually free to check.

2. Matching is greedy, not globally optimal: build a full similarity
   matrix, then repeatedly take the single highest remaining score and
   lock in that pair. A real optimal-assignment algorithm (the Hungarian
   algorithm) exists and would handle certain tricky cases better — but
   greedy is far simpler to reason about, and for real documents (where
   most paragraphs don't have many plausible look-alikes to confuse a
   greedy choice) it produces the same result in the vast majority of
   cases. Same category of tradeoff as the row/page matching limitations
   already documented in table_diff.py and visual_diff.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from app.diff_engine import DiffSegment, compare_text
from app.embeddings import get_embedding_provider

# (min_similarity, tier_label) — checked in order, first match wins.
# These boundaries are also used to compute "confidence": a score sitting
# right on a boundary is a much shakier classification than one sitting
# comfortably in the middle of a tier.
_TIER_THRESHOLDS = [0.95, 0.80, 0.55]
_TIER_LABELS = ["minor_wording_change", "semantically_similar", "meaningful_change", "major_change"]

_CONFIDENCE_MARGIN = 0.05  # closer than this to a tier boundary => "low" confidence


@dataclass
class ParagraphMatch:
    type: str  # "exact_match" | one of _TIER_LABELS | "added" | "removed"
    original: str | None = None
    modified: str | None = None
    similarity: float | None = None  # None only for "added"/"removed"
    # Only meaningful for model-derived classifications — exact_match is
    # deterministic (always effectively 100% confident) and added/removed
    # aren't a similarity judgment at all, so both leave this as None
    # rather than implying a confidence level that doesn't apply.
    confidence: str | None = None
    # Word-level diff segments scoped specifically to this paragraph pair —
    # allows side-by-side views to render fine-grained "this word changed"
    # highlighting within row-aligned clauses.
    segments: list[DiffSegment] = field(default_factory=list)


@dataclass
class SemanticDiff:
    provider: str  # which embedding provider actually produced these scores
    matches: list[ParagraphMatch] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _split_paragraphs(text: str) -> list[str]:
    # Prefer real paragraph breaks (blank lines). If that yields only one
    # block — e.g. text that was already flattened line-by-line, like a
    # spreadsheet's "sheet: cell | cell" rows from Phase 5 — fall back to
    # splitting on single newlines instead, so spreadsheet-derived text
    # still gets compared line-by-line rather than as one giant "paragraph."
    blocks = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(blocks) > 1:
        return blocks
    return [line.strip() for line in text.splitlines() if line.strip()]


def _classify(similarity: float) -> str:
    for threshold, label in zip(_TIER_THRESHOLDS, _TIER_LABELS):
        if similarity >= threshold:
            return label
    return _TIER_LABELS[-1]


def _confidence(similarity: float) -> str:
    margin = min(abs(similarity - t) for t in _TIER_THRESHOLDS)
    return "high" if margin > _CONFIDENCE_MARGIN else "low"


def _compute_match_segments(
    match_type: str, original: str | None, modified: str | None
) -> list[DiffSegment]:
    if match_type == "exact_match":
        text = original if original is not None else (modified or "")
        return [DiffSegment(type="equal", original=text, modified=text)]
    orig = original or ""
    mod = modified or ""
    return compare_text(orig, mod).segments


def _order_matches(
    indexed_matches: list[tuple[int | None, int | None, ParagraphMatch]],
) -> list[ParagraphMatch]:
    """Orders matches to follow document flow.

    Exact and reworded pairs are anchored by their original paragraph index.
    Added paragraphs (which have no original index) are interpolated relative
    to neighboring matched modified paragraphs, ensuring they appear at the
    point in the document where they were inserted rather than grouped at the end.
    """
    if not indexed_matches:
        return []

    matched_mod_to_orig = {
        m_idx: o_idx
        for o_idx, m_idx, _ in indexed_matches
        if o_idx is not None and m_idx is not None
    }
    sorted_matched_mods = sorted(matched_mod_to_orig.keys())

    def sort_key(item: tuple[int | None, int | None, ParagraphMatch]) -> tuple[float, int, int]:
        orig_idx, mod_idx, _ = item
        if orig_idx is not None:
            return (float(orig_idx), orig_idx, mod_idx if mod_idx is not None else -1)

        # Added paragraph: interpolate position using neighboring matched modified paragraphs
        assert mod_idx is not None
        if not sorted_matched_mods:
            return (float(mod_idx), -1, mod_idx)

        prev_m = max((m for m in sorted_matched_mods if m < mod_idx), default=None)
        next_m = min((m for m in sorted_matched_mods if m > mod_idx), default=None)

        if prev_m is not None and next_m is not None:
            prev_orig = matched_mod_to_orig[prev_m]
            next_orig = matched_mod_to_orig[next_m]
            fraction = (mod_idx - prev_m) / (next_m - prev_m)
            est = prev_orig + fraction * (next_orig - prev_orig)
        elif prev_m is not None:
            est = matched_mod_to_orig[prev_m] + 0.5 + 0.01 * (mod_idx - prev_m)
        elif next_m is not None:
            est = matched_mod_to_orig[next_m] - 0.5 + 0.01 * (mod_idx - next_m)
        else:
            est = float(mod_idx)

        return (est, -1, mod_idx)

    return [m for _, _, m in sorted(indexed_matches, key=sort_key)]


def _match_remaining(
    unmatched_original: list[tuple[int, str]],
    unmatched_modified: list[tuple[int, str]],
) -> tuple[list[tuple[int | None, int | None, ParagraphMatch]], dict[str, int]]:
    stats = {label: 0 for label in _TIER_LABELS} | {"added": 0, "removed": 0}
    indexed_matches: list[tuple[int | None, int | None, ParagraphMatch]] = []

    if not unmatched_original or not unmatched_modified:
        for orig_idx, text in unmatched_original:
            match = ParagraphMatch(
                type="removed",
                original=text,
                segments=_compute_match_segments("removed", text, None),
            )
            indexed_matches.append((orig_idx, None, match))
            stats["removed"] += 1
        for mod_idx, text in unmatched_modified:
            match = ParagraphMatch(
                type="added",
                modified=text,
                segments=_compute_match_segments("added", None, text),
            )
            indexed_matches.append((None, mod_idx, match))
            stats["added"] += 1
        return indexed_matches, stats

    original_texts = [text for _, text in unmatched_original]
    modified_texts = [text for _, text in unmatched_modified]

    provider = get_embedding_provider()
    sim_matrix = np.clip(provider.similarity_matrix(original_texts, modified_texts), 0.0, 1.0)

    available_rows = set(range(len(unmatched_original)))
    available_cols = set(range(len(unmatched_modified)))

    # Take the single highest-scoring pair repeatedly, skipping any
    # row/col already claimed by an earlier (higher-scoring) pick. The
    # paragraph counts here are small enough that a full argsort is cheap
    # — no need for anything cleverer.
    flat_order = np.dstack(np.unravel_index(np.argsort(-sim_matrix, axis=None), sim_matrix.shape))[0]

    for row, col in flat_order:
        row, col = int(row), int(col)
        if row not in available_rows or col not in available_cols:
            continue
        similarity = float(sim_matrix[row, col])
        tier = _classify(similarity)
        orig_idx, orig_text = unmatched_original[row]
        mod_idx, mod_text = unmatched_modified[col]
        match = ParagraphMatch(
            type=tier,
            original=orig_text,
            modified=mod_text,
            similarity=round(similarity, 4),
            confidence=_confidence(similarity),
            segments=_compute_match_segments(tier, orig_text, mod_text),
        )
        indexed_matches.append((orig_idx, mod_idx, match))
        stats[tier] += 1
        available_rows.discard(row)
        available_cols.discard(col)

    for row in available_rows:
        orig_idx, orig_text = unmatched_original[row]
        match = ParagraphMatch(
            type="removed",
            original=orig_text,
            segments=_compute_match_segments("removed", orig_text, None),
        )
        indexed_matches.append((orig_idx, None, match))
        stats["removed"] += 1

    for col in available_cols:
        mod_idx, mod_text = unmatched_modified[col]
        match = ParagraphMatch(
            type="added",
            modified=mod_text,
            segments=_compute_match_segments("added", None, mod_text),
        )
        indexed_matches.append((None, mod_idx, match))
        stats["added"] += 1

    return indexed_matches, stats


def compare_semantic(original_text: str, modified_text: str) -> SemanticDiff:
    original_paragraphs = _split_paragraphs(original_text)
    modified_paragraphs = _split_paragraphs(modified_text)

    stats = {"exact_match": 0}
    indexed_matches: list[tuple[int | None, int | None, ParagraphMatch]] = []

    # Deterministic pass first (see module docstring): pull out exact
    # string matches before any similarity model gets involved at all.
    modified_pool = list(enumerate(modified_paragraphs))
    claimed_modified: set[int] = set()
    unmatched_original: list[tuple[int, str]] = []

    for orig_idx, original_paragraph in enumerate(original_paragraphs):
        match_index = next(
            (i for i, text in modified_pool if i not in claimed_modified and text == original_paragraph),
            None,
        )
        if match_index is not None:
            match = ParagraphMatch(
                type="exact_match",
                original=original_paragraph,
                modified=original_paragraph,
                similarity=1.0,
                segments=_compute_match_segments("exact_match", original_paragraph, original_paragraph),
            )
            indexed_matches.append((orig_idx, match_index, match))
            stats["exact_match"] += 1
            claimed_modified.add(match_index)
        else:
            unmatched_original.append((orig_idx, original_paragraph))

    unmatched_modified = [(i, text) for i, text in modified_pool if i not in claimed_modified]

    provider_name = get_embedding_provider().name if (unmatched_original and unmatched_modified) else "n/a"
    remaining_matches, remaining_stats = _match_remaining(unmatched_original, unmatched_modified)

    indexed_matches.extend(remaining_matches)
    stats.update(remaining_stats)

    sorted_matches = _order_matches(indexed_matches)

    return SemanticDiff(provider=provider_name, matches=sorted_matches, stats=stats)
