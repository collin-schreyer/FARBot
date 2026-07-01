"""Retrieval metrics for the FAR bot eval harness (pure functions).

A "match" = a retrieved citation whose section number starts with an expected
section prefix (e.g. expected "52.219" matches retrieved "52.219-6"). This mirrors
the prefix logic used in python/analyze_search_quality.py so numbers are comparable
to the documented baselines.
"""
from typing import List, Sequence


def _norm(citation: str) -> str:
    return citation.strip().lstrip("[").rstrip("]").strip()


def _matches(citation: str, expected: str) -> bool:
    return _norm(citation).startswith(expected)


def any_match(citations: Sequence[str], expected: Sequence[str]) -> bool:
    return any(_matches(c, e) for c in citations for e in expected)


def recall_at_k(citations: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Fraction of expected sections found anywhere in the top-k citations."""
    if not expected:
        return 0.0
    top = citations[:k]
    found = sum(any(_matches(c, e) for c in top) for e in expected)
    return found / len(expected)


def hit_at_k(citations: Sequence[str], expected: Sequence[str], k: int) -> float:
    """1.0 if any expected section appears in the top-k, else 0.0."""
    return 1.0 if any_match(citations[:k], expected) else 0.0


def mrr(citations: Sequence[str], expected: Sequence[str]) -> float:
    """Reciprocal rank of the first relevant citation."""
    for i, c in enumerate(citations, 1):
        if any(_matches(c, e) for e in expected):
            return 1.0 / i
    return 0.0


def precision_relevant_at_k(citations: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Fraction of the top-k citations that match ANY expected section.

    This is the metric the documented baselines report (top-3 relevance %).
    """
    top = citations[:k]
    if not top:
        return 0.0
    rel = sum(1 for c in top if any(_matches(c, e) for e in expected))
    return rel / len(top)
