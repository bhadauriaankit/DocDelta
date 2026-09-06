"""
Phase 1 diff engine.

Deliberately simple and deterministic: this module has ONE job, take two
strings and return a structured list of differences. No AI, no formatting
awareness, no layout — that comes in later phases. Keeping this function
pure (no I/O, no side effects) makes it trivial to unit test, which matters
because this is the "ground truth" every later comparison layer builds on.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field


@dataclass
class DiffSegment:
    """One chunk of a word-level diff."""

    type: str  # "equal" | "added" | "removed" | "replaced"
    original: str = ""
    modified: str = ""


@dataclass
class DiffResult:
    similarity: float  # 0.0 - 1.0
    segments: list[DiffSegment] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


_WORD_RE = re.compile(r"\S+|\s+")


def _tokenize(text: str) -> list[str]:
    """Split into words + whitespace, keeping whitespace as its own tokens
    so we can reconstruct spacing exactly and (later) flag whitespace-only
    changes separately from real content changes."""
    return _WORD_RE.findall(text)


def compare_text(original: str, modified: str) -> DiffResult:
    """Word-level diff between two plain-text strings."""
    original_tokens = _tokenize(original)
    modified_tokens = _tokenize(modified)

    matcher = difflib.SequenceMatcher(a=original_tokens, b=modified_tokens, autojunk=False)

    segments: list[DiffSegment] = []
    stats = {"added": 0, "removed": 0, "replaced": 0, "equal": 0}

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        orig_chunk = "".join(original_tokens[i1:i2])
        mod_chunk = "".join(modified_tokens[j1:j2])

        if tag == "equal":
            segments.append(DiffSegment(type="equal", original=orig_chunk, modified=mod_chunk))
            stats["equal"] += 1
        elif tag == "delete":
            segments.append(DiffSegment(type="removed", original=orig_chunk))
            stats["removed"] += 1
        elif tag == "insert":
            segments.append(DiffSegment(type="added", modified=mod_chunk))
            stats["added"] += 1
        elif tag == "replace":
            segments.append(DiffSegment(type="replaced", original=orig_chunk, modified=mod_chunk))
            stats["replaced"] += 1

    similarity = matcher.ratio()

    return DiffResult(similarity=round(similarity, 4), segments=segments, stats=stats)
