"""
apps/testing/services/question_selector.py

Question selection and distribution logic for test attempts.

Key design decisions:
  - TOTAL_QUESTIONS is derived from DEFAULT_DISTRIBUTION, never hardcoded.
  - The distribution can be overridden via Django settings (TEST_QUESTION_DISTRIBUTION).
  - If the configured distribution total != expected total, a clear ImproperlyConfigured
    error is raised at import time — fast fail, no silent corruption.
  - All public functions are side-effect free; DB writes live in callers.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db.models import Prefetch

# ---------------------------------------------------------------------------
# Distribution configuration
# ---------------------------------------------------------------------------

#: Canonical ordering of question types — used to keep behaviour deterministic
#: across Python dict orderings (3.7+ dicts are ordered, but being explicit is safer).
QUESTION_TYPES: List[str] = [
    "single_choice",
    "multiple_choice",
    "text",
    "code",
]

#: Default per-type quotas.  Sum = 20.
DEFAULT_DISTRIBUTION: Dict[str, int] = {
    "single_choice": 9,
    "multiple_choice": 9,
    "text": 1,
    "code": 1,
}

# ---------------------------------------------------------------------------
# Load (and validate) the distribution at module import time
# ---------------------------------------------------------------------------

def _load_distribution() -> Dict[str, int]:
    """
    Return the active distribution dict from Django settings or the default.

    Raises ImproperlyConfigured if:
      - The distribution contains unknown question types.
      - Any quota is not a positive integer.
      - The distribution is empty.
    """
    dist: Dict[str, int] = getattr(
        settings,
        "TEST_QUESTION_DISTRIBUTION",
        DEFAULT_DISTRIBUTION,
    )

    if not dist:
        raise ImproperlyConfigured(
            "TEST_QUESTION_DISTRIBUTION must not be empty."
        )

    unknown = set(dist) - set(QUESTION_TYPES)
    if unknown:
        raise ImproperlyConfigured(
            f"TEST_QUESTION_DISTRIBUTION contains unknown question types: "
            f"{sorted(unknown)}. "
            f"Valid types: {QUESTION_TYPES}."
        )

    for qtype, quota in dist.items():
        if not isinstance(quota, int) or quota < 0:
            raise ImproperlyConfigured(
                f"TEST_QUESTION_DISTRIBUTION['{qtype}'] must be a non-negative integer, "
                f"got {quota!r}."
            )

    return dict(dist)


#: Active distribution (validated at import time).
QUESTION_DISTRIBUTION: Dict[str, int] = _load_distribution()

#: Total questions per attempt — derived from distribution, never hardcoded.
TOTAL_QUESTIONS: int = sum(QUESTION_DISTRIBUTION.values())

# Sanity-check: must be positive
if TOTAL_QUESTIONS <= 0:
    raise ImproperlyConfigured(
        f"TEST_QUESTION_DISTRIBUTION sums to {TOTAL_QUESTIONS}; "
        "it must sum to a positive integer."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_distribution_total(distribution: Dict[str, int]) -> None:
    """Assert that a computed distribution still sums to TOTAL_QUESTIONS."""
    total = sum(distribution.values())
    if total != TOTAL_QUESTIONS:
        raise ValidationError(
            f"Internal distribution error: expected {TOTAL_QUESTIONS} total questions, "
            f"got {total}. Distribution: {distribution}. "
            "This is a bug — please report it."
        )


def _compute_distribution(available_types: List[str]) -> Dict[str, int]:
    """
    Return per-type quotas for the given *available_types*.

    Algorithm:
      1. Start from QUESTION_DISTRIBUTION.
      2. For each type that is NOT available, add its quota to a 'missing' pool.
      3. Redistribute the missing pool evenly across the available types
         (remainder distributed to the first types in QUESTION_TYPES order).

    Args:
        available_types: Question types that actually exist in the test.

    Returns:
        Dict mapping each available type to its final quota.

    Raises:
        ValidationError: If available_types is empty or contains unknown types.
    """
    if not available_types:
        return {}

    unknown = set(available_types) - set(QUESTION_TYPES)
    if unknown:
        raise ValidationError(
            f"Unknown question types in available_types: {sorted(unknown)}."
        )

    distribution: Dict[str, int] = {}
    missing_quota = 0

    for qtype in QUESTION_TYPES:
        configured = QUESTION_DISTRIBUTION.get(qtype, 0)
        if qtype in available_types:
            distribution[qtype] = configured
        else:
            missing_quota += configured

    if missing_quota == 0:
        # All configured types are available — nothing to redistribute.
        return distribution

    # Redistribute missing quota across available types (in canonical order).
    REDISTRIBUTABLE_TYPES = [
        "single_choice",
        "multiple_choice",
    ]

    available_ordered = [
        qt
        for qt in REDISTRIBUTABLE_TYPES
        if qt in distribution
    ]
    base_extra, remainder = divmod(missing_quota, len(available_ordered))

    for idx, qtype in enumerate(available_ordered):
        distribution[qtype] += base_extra
        if idx < remainder:
            distribution[qtype] += 1

    _validate_distribution_total(distribution)
    return distribution


def _fill_to_n(pool: List[Any], n: int, rng: random.Random) -> List[Any]:
    """
    Select exactly *n* items from *pool*.

    - pool >= n  → random sample without replacement.
    - pool < n   → repeat-sample until n reached, avoiding consecutive duplicates
                   where possible (good UX for small question banks).

    Raises ValidationError if pool is empty.
    """
    if not pool:
        raise ValidationError("Cannot sample from an empty question pool.")

    if len(pool) >= n:
        return rng.sample(pool, n)

    result: List[Any] = []
    last_id: Any = None

    while len(result) < n:
        candidates = [q for q in pool if getattr(q, "id", None) != last_id]
        if not candidates:
            candidates = pool
        chosen = rng.choice(candidates)
        result.append(chosen)
        last_id = getattr(chosen, "id", None)

    return result


def _serialize_question(question: Any) -> Dict[str, Any]:
    """Serialize a Question model instance to a plain dict (no correct-answer leakage)."""
    item: Dict[str, Any] = {
        "id": str(question.id),
        "text": question.text,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "order": question.order,
        "is_auto_gradable": question.is_auto_gradable,
    }

    if getattr(question, "language", None):
        item["language"] = question.language

    if getattr(question, "metadata", None):
        item["metadata"] = question.metadata

    if question.question_type in ("single_choice", "multiple_choice"):
        options_qs = getattr(question, "cached_options", None)
        if options_qs is None:
            options_qs = question.options.all()
        item["options"] = [
            {"id": str(opt.id), "text": opt.text, "order": opt.order}
            for opt in sorted(options_qs, key=lambda o: o.order)
        ]

    return item


def _seed_from_attempt_id(attempt_id: str) -> int:
    """Derive a deterministic integer seed from a UUID string."""
    return int(attempt_id.replace("-", ""), 16) % (2 ** 31)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_questions_for_attempt(
    test_id: str,
    seed: Optional[int] = None,
    attempt_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build a deterministic, distribution-respecting question set for one attempt.

    Priority for seed resolution: explicit *seed* > *attempt_id* > None (random).

    Args:
        test_id:    PK of the Test.
        seed:       Optional explicit RNG seed.
        attempt_id: Optional attempt UUID used to derive a seed automatically.

    Returns:
        List of serialized question dicts (length == TOTAL_QUESTIONS when the
        test has enough questions; may be shorter only if the bank itself is
        smaller and repeat-sampling still can't reach the quota — shouldn't
        happen in practice).

    Raises:
        ValidationError: If the test has no questions at all.
    """
    from ..models import Question

    resolved_seed: Optional[int] = seed
    if resolved_seed is None and attempt_id is not None:
        resolved_seed = _seed_from_attempt_id(attempt_id)

    rng = random.Random(resolved_seed)

    all_questions = list(
        Question.objects
        .filter(test_id=test_id)
        .prefetch_related(Prefetch("options", to_attr="cached_options"))
        .order_by("id")  # stable ordering before random selection
    )

    if not all_questions:
        raise ValidationError(f"Test {test_id} has no questions.")

    # Group by type
    grouped: Dict[str, List[Any]] = defaultdict(list)
    for q in all_questions:
        grouped[q.question_type].append(q)

    available_types = [qt for qt in QUESTION_TYPES if grouped.get(qt)]
    distribution = _compute_distribution(available_types)

    selected: List[Any] = []
    for qtype in available_types:
        quota = distribution[qtype]
        chosen = _fill_to_n(pool=grouped[qtype], n=quota, rng=rng)
        selected.extend(chosen)

    rng.shuffle(selected)
    return [_serialize_question(q) for q in selected]


def validate_attempt_structure(answers: List[Dict[str, Any]]) -> None:
    """
    Validate that a submitted answer list matches the expected distribution.

    Checks:
      - answers is a list.
      - Length equals TOTAL_QUESTIONS.
      - All question_type values are valid.
      - Per-type counts match the computed distribution for those types.

    Raises:
        ValidationError: On any violation.
    """
    if not isinstance(answers, list):
        raise ValidationError("answers must be a list.")

    if len(answers) != TOTAL_QUESTIONS:
        raise ValidationError(
            f"Expected exactly {TOTAL_QUESTIONS} answers, got {len(answers)}."
        )

    type_counts: Dict[str, int] = defaultdict(int)

    for idx, answer in enumerate(answers):
        qtype = (
            answer.get("question_type")
            or (answer.get("question") or {}).get("question_type")
        )
        if not qtype:
            raise ValidationError(
                f"Answer at index {idx} is missing question_type."
            )
        if qtype not in QUESTION_TYPES:
            raise ValidationError(
                f"Unknown question_type='{qtype}' at index {idx}."
            )
        type_counts[qtype] += 1

    present_types = [qt for qt in QUESTION_TYPES if type_counts.get(qt, 0) > 0]
    expected = _compute_distribution(present_types)

    violations: List[str] = []
    for qtype in present_types:
        exp = expected.get(qtype, 0)
        act = type_counts.get(qtype, 0)
        if exp != act:
            violations.append(f"'{qtype}': expected {exp}, got {act}")

    if violations:
        raise ValidationError(
            "Attempt structure invalid:\n" + "\n".join(violations)
        )


def build_attempt_questions(test_id: str, attempt_id: str) -> List[Dict[str, Any]]:
    """
    Convenience wrapper: build questions for a specific attempt (uses attempt_id as seed).

    Args:
        test_id:    PK of the Test.
        attempt_id: PK of the StudentAttempt.

    Returns:
        List of serialized question dicts.
    """
    return get_questions_for_attempt(test_id=test_id, attempt_id=attempt_id)