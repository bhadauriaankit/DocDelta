"""
Formatting-level comparison: font, size, bold/italic/underline, and
dominant color — for DOCX and PDF documents.

Scoped to these two formats: "font" is a meaningful, reliably extractable
concept for a word-processor document or a PDF's rendered text. It's not
really meaningful for XLSX/CSV (a spreadsheet cell's font is rarely the
point of a comparison), and PPTX slide formatting is a reasonable future
extension, not covered here.

Granularity is per-PARAGRAPH, not per-run/per-span. A paragraph can mix
multiple fonts/styles (one bold word inside an otherwise plain sentence)
— this reports whether ANY text in the paragraph is bold/italic and the
DOMINANT (most common) font/size/color, rather than diffing every
individual run. Character-by-character formatting diffing is a
meaningfully harder problem — run/span boundaries between two versions of
a document rarely line up cleanly even when the visible formatting looks
identical — and is a reasonable future improvement, not in scope here.
Same category of documented boundary as the row/page/paragraph matching
limits elsewhere in this project (table_diff.py, visual_diff.py,
semantic_diff.py all state one).

Paragraphs are matched between documents by text similarity (the same
greedy approach as semantic_diff.py, via app.embeddings), not position —
a reordered paragraph is still compared against itself. Below a
similarity floor, two paragraphs are treated as unrelated (one removed,
one added) rather than reported as "formatting changed" between content
that isn't really the same paragraph at all — a low-confidence pairing
there would be actively misleading, not just imprecise.
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass, field

import docx
import fitz
import numpy as np

from app.embeddings import get_embedding_provider

# Below this similarity, don't pair two paragraphs at all — see module
# docstring for why. semantic_diff.py doesn't need an equivalent because
# every pairing there gets an honest low score ("major_change") rather
# than a specific formatting claim that implies "this IS the same content."
_MATCH_THRESHOLD = 0.5

_BOLD_FLAG = 1 << 4  # confirmed empirically against a real PyMuPDF-rendered PDF, not assumed
_ITALIC_FLAG = 1 << 1


@dataclass
class ParagraphFormatting:
    text: str
    font: str | None = None
    size: float | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None  # hex RGB, e.g. "FF0000"; None if default/unavailable


@dataclass
class FormattingChange:
    type: str  # "unchanged" | "changed" | "added" | "removed"
    original_text: str | None = None
    modified_text: str | None = None
    # e.g. {"font": {"from": "Calibri", "to": "Arial"}, "bold": {"from": False, "to": True}}
    changed_properties: dict = field(default_factory=dict)


@dataclass
class FormattingDiff:
    changes: list[FormattingChange] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=lambda: {"unchanged": 0, "changed": 0, "added": 0, "removed": 0})


def _most_common(values: list) -> object | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return Counter(present).most_common(1)[0][0]


def extract_formatting_docx(raw: bytes) -> list[ParagraphFormatting]:
    document = docx.Document(io.BytesIO(raw))
    results: list[ParagraphFormatting] = []

    for paragraph in document.paragraphs:
        if not paragraph.text.strip():
            continue

        fonts, sizes, colors = [], [], []
        bold = italic = underline = False

        for run in paragraph.runs:
            if run.font.name:
                fonts.append(run.font.name)
            if run.font.size:
                sizes.append(run.font.size.pt)
            if run.bold:
                bold = True
            if run.italic:
                italic = True
            if run.underline:
                underline = True
            try:
                if run.font.color and run.font.color.type is not None:
                    colors.append(str(run.font.color.rgb))
            except AttributeError:
                pass  # theme colors / unusual color definitions — skip rather than guess

        results.append(
            ParagraphFormatting(
                text=paragraph.text,
                font=_most_common(fonts),
                size=_most_common(sizes),
                bold=bold,
                italic=italic,
                underline=underline,
                color=_most_common(colors),
            )
        )

    return results


def extract_formatting_pdf(raw: bytes) -> list[ParagraphFormatting]:
    document = fitz.open(stream=raw, filetype="pdf")
    results: list[ParagraphFormatting] = []

    try:
        for page in document:
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # 0 = text block; skip images
                    continue

                text_parts, fonts, sizes, colors = [], [], [], []
                bold = italic = False

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text_parts.append(span.get("text", ""))
                        if span.get("font"):
                            fonts.append(span["font"])
                        if span.get("size"):
                            sizes.append(round(span["size"], 1))
                        flags = span.get("flags", 0)
                        if flags & _BOLD_FLAG:
                            bold = True
                        if flags & _ITALIC_FLAG:
                            italic = True
                        color_int = span.get("color")
                        if color_int is not None:
                            colors.append(f"{color_int:06X}")

                text = "".join(text_parts).strip()
                if not text:
                    continue

                results.append(
                    ParagraphFormatting(
                        text=text,
                        font=_most_common(fonts),
                        size=_most_common(sizes),
                        bold=bold,
                        italic=italic,
                        underline=False,  # PyMuPDF's span flags don't reliably expose underline — not guessing
                        color=_most_common(colors),
                    )
                )
    finally:
        document.close()

    return results


def extract_formatting(fmt: str, raw: bytes) -> list[ParagraphFormatting] | None:
    """Returns None for formats this module doesn't support — callers use
    that to decide whether formatting comparison applies at all."""
    if fmt == "docx":
        return extract_formatting_docx(raw)
    if fmt == "pdf":
        return extract_formatting_pdf(raw)
    return None


def _diff_properties(a: ParagraphFormatting, b: ParagraphFormatting) -> dict:
    changed = {}
    for prop in ("font", "size", "bold", "italic", "underline", "color"):
        a_value, b_value = getattr(a, prop), getattr(b, prop)
        if a_value != b_value:
            changed[prop] = {"from": a_value, "to": b_value}
    return changed


def _record_pair(
    original: ParagraphFormatting, modified: ParagraphFormatting, changes: list[FormattingChange], stats: dict
) -> None:
    changed_properties = _diff_properties(original, modified)
    if changed_properties:
        changes.append(
            FormattingChange(
                type="changed",
                original_text=original.text,
                modified_text=modified.text,
                changed_properties=changed_properties,
            )
        )
        stats["changed"] += 1
    else:
        changes.append(FormattingChange(type="unchanged", original_text=original.text, modified_text=modified.text))
        stats["unchanged"] += 1


def compare_formatting(original: list[ParagraphFormatting], modified: list[ParagraphFormatting]) -> FormattingDiff:
    stats = {"unchanged": 0, "changed": 0, "added": 0, "removed": 0}
    changes: list[FormattingChange] = []

    if not original or not modified:
        for p in original:
            changes.append(FormattingChange(type="removed", original_text=p.text))
            stats["removed"] += 1
        for p in modified:
            changes.append(FormattingChange(type="added", modified_text=p.text))
            stats["added"] += 1
        return FormattingDiff(changes=changes, stats=stats)

    original_texts = [p.text for p in original]
    modified_texts = [p.text for p in modified]

    # Exact text matches first (deterministic) — same principle as
    # semantic_diff.py: don't let a similarity model weigh in on
    # paragraphs that are provably identical.
    claimed_modified: set[int] = set()
    exact_pairs: list[tuple[int, int]] = []
    unmatched_original_idx: list[int] = []

    for oi, o_text in enumerate(original_texts):
        match = next(
            (mi for mi, m_text in enumerate(modified_texts) if mi not in claimed_modified and m_text == o_text),
            None,
        )
        if match is not None:
            exact_pairs.append((oi, match))
            claimed_modified.add(match)
        else:
            unmatched_original_idx.append(oi)

    unmatched_modified_idx = [mi for mi in range(len(modified_texts)) if mi not in claimed_modified]

    for oi, mi in exact_pairs:
        _record_pair(original[oi], modified[mi], changes, stats)

    if unmatched_original_idx and unmatched_modified_idx:
        provider = get_embedding_provider()
        o_texts = [original_texts[i] for i in unmatched_original_idx]
        m_texts = [modified_texts[i] for i in unmatched_modified_idx]
        sim_matrix = np.clip(provider.similarity_matrix(o_texts, m_texts), 0.0, 1.0)

        available_rows = set(range(len(o_texts)))
        available_cols = set(range(len(m_texts)))
        flat_order = np.dstack(np.unravel_index(np.argsort(-sim_matrix, axis=None), sim_matrix.shape))[0]

        for row, col in flat_order:
            row, col = int(row), int(col)
            if row not in available_rows or col not in available_cols:
                continue
            if sim_matrix[row, col] < _MATCH_THRESHOLD:
                continue  # too dissimilar to treat as "the same paragraph" — see module docstring
            oi, mi = unmatched_original_idx[row], unmatched_modified_idx[col]
            _record_pair(original[oi], modified[mi], changes, stats)
            available_rows.discard(row)
            available_cols.discard(col)

        for row in available_rows:
            oi = unmatched_original_idx[row]
            changes.append(FormattingChange(type="removed", original_text=original_texts[oi]))
            stats["removed"] += 1
        for col in available_cols:
            mi = unmatched_modified_idx[col]
            changes.append(FormattingChange(type="added", modified_text=modified_texts[mi]))
            stats["added"] += 1
    else:
        for oi in unmatched_original_idx:
            changes.append(FormattingChange(type="removed", original_text=original_texts[oi]))
            stats["removed"] += 1
        for mi in unmatched_modified_idx:
            changes.append(FormattingChange(type="added", modified_text=modified_texts[mi]))
            stats["added"] += 1

    return FormattingDiff(changes=changes, stats=stats)
