"""Explicit, experimental near-duplicate policy for frozen candidate pools.

No production defaults: callers supply and record developer-calibrated thresholds.
Unknown evidence must not be counted as proof of distinct dishes.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol

from app.planning.recipe_pair_similarity import RecipePairSignals


@dataclass(frozen=True)
class NearDuplicatePolicy:
    version: str
    title_min: float
    ingredients_min: float
    cosine_min: float
    fried_rice_cosine_min: float | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("A recorded policy version is required")
        for value in (self.title_min, self.ingredients_min, self.cosine_min):
            if not isfinite(value) or not 0 < value <= 1:
                raise ValueError("Thresholds must be finite and in (0, 1]")
        if self.fried_rice_cosine_min is not None and (
            not isfinite(self.fried_rice_cosine_min) or not 0 < self.fried_rice_cosine_min <= self.cosine_min
        ):
            raise ValueError("Preparation threshold must be positive and no higher than the general cosine threshold")


def classify(signals: RecipePairSignals, policy: NearDuplicatePolicy) -> Literal["near", "distinct", "unknown"]:
    """Conjunction of three signals. Missing evidence stays unknown, not distinct.

    The optional fried-rice threshold is an explicit developer policy choice;
    it still requires title and ingredient evidence and available vectors.
    Existing policies retain their general threshold.
    """
    values = (signals.title_overlap, signals.ingredient_overlap, signals.vector_cosine)
    if signals.vector_status != "available" or any(value is None or not isfinite(value) for value in values):
        return "unknown"
    if not (0 <= values[0] <= 1 and 0 <= values[1] <= 1 and -1 <= values[2] <= 1):
        return "unknown"
    cosine_min = policy.cosine_min
    if signals.shared_preparation == "fried_rice" and policy.fried_rice_cosine_min is not None:
        cosine_min = policy.fried_rice_cosine_min
    return (
        "near"
        if all(
            value >= limit
            for value, limit in zip(values, (policy.title_min, policy.ingredients_min, cosine_min), strict=True)
        )
        else "distinct"
    )


class PairIndex(Protocol):
    def compare(self, left_key: str, right_key: str) -> RecipePairSignals: ...


@dataclass(frozen=True)
class DishGroups:
    policy: NearDuplicatePolicy
    groups: tuple[tuple[str, ...], ...]
    unknown_pairs: tuple[tuple[str, str], ...]
    # Near pairs crossing groups are retained: groups alone do not capture all
    # similarity, since similarity is not transitive.
    near_pairs: tuple[tuple[str, str], ...]


def group_candidates(keys: list[str], index: PairIndex, policy: NearDuplicatePolicy) -> DishGroups:
    """Stable complete-link groups: every pair within a group must be near.

    Visit stable keys, joining the first compatible group. This is deterministic,
    not an optimum clustering claim. Return unresolved and cross-group pair
    evidence so a later score/validator never treats group count as proven variety.
    """
    if len(set(keys)) != len(keys):
        raise ValueError("Candidate keys must be unique")
    ordered = sorted(keys)
    verdicts = {
        (left, right): classify(index.compare(left, right), policy)
        for position, left in enumerate(ordered)
        for right in ordered[position + 1 :]
    }
    groups: list[list[str]] = []
    for key in ordered:
        group = next((group for group in groups if all(verdicts[(member, key)] == "near" for member in group)), None)
        if group is None:
            groups.append([key])
        else:
            group.append(key)
    return DishGroups(
        policy,
        tuple(tuple(group) for group in groups),
        tuple(pair for pair, verdict in verdicts.items() if verdict == "unknown"),
        tuple(pair for pair, verdict in verdicts.items() if verdict == "near"),
    )
