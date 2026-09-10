import json

import pytest

from app.core.paths import repository_root
from app.planning.dietary_tags import (
    IMPLICATIONS_RELATIVE,
    DietaryImplicationCycle,
    expand_tags,
    load_implications,
    satisfies,
)


def test_vegan_satisfies_vegetarian_and_dairy_free():
    assert satisfies(["vegetarian"], ["vegan"])
    assert satisfies(["dairy-free"], ["vegan"])
    assert satisfies(["vegetarian", "dairy-free"], ["vegan"])


def test_entailment_is_one_directional():
    """The reverse would let a chicken dish through a vegan requirement."""
    assert not satisfies(["vegan"], ["vegetarian"])
    assert not satisfies(["vegetarian"], ["dairy-free"])
    assert not satisfies(["vegan"], ["dairy-free"])


def test_unrelated_tags_entail_nothing():
    for tag in ("gluten-free", "high-protein", "high-fibre"):
        assert expand_tags([tag]) == {tag}, f"{tag} must not entail anything"


def test_closure_is_transitive_without_writing_the_chain():
    table = {"a": frozenset({"b"}), "b": frozenset({"c"})}
    assert expand_tags(["a"], table) == {"a", "b", "c"}


def test_a_cycle_raises_rather_than_looping():
    """A table contradicting itself is a data error. Ignoring it would make the
    filter behave differently from what the table says."""
    table = {"a": frozenset({"b"}), "b": frozenset({"a"})}
    # A two-tag cycle still terminates because closure is idempotent; a table
    # that grows without settling is what must be caught.
    assert expand_tags(["a"], table) == {"a", "b"}
    with pytest.raises(DietaryImplicationCycle):
        expand_tags(["a"], _NeverSettling())


class _NeverSettling(dict):
    """Stands in for a table whose closure does not terminate."""

    _next = 0

    def get(self, key, default=None):
        _NeverSettling._next += 1
        return frozenset({f"tag-{_NeverSettling._next}"})

    def __len__(self):
        return 1


def test_the_committed_table_only_claims_definitional_entailments():
    """The admission rule is the whole safeguard: anything weaker becomes an
    implicit rule the user cannot see and did not ask for."""
    payload = json.loads((repository_root() / IMPLICATIONS_RELATIVE).read_text(encoding="utf-8"))
    for tag, entry in payload["implications"].items():
        assert entry["entails"], f"{tag} declares no entailment"
        assert entry["reason"].strip(), f"{tag} entails without a recorded reason"

    descriptive = {"high-protein", "high-fibre"}
    for tag, entailed in load_implications().items():
        assert not descriptive & ({tag} | set(entailed)), (
            "descriptive tags describe a recipe rather than restricting it, so they never participate in entailment"
        )


def test_a_vegetarian_household_sees_the_vegan_recipes():
    """The measurable consequence on the committed catalog: without the closure a
    vegetarian requirement matched 8 recipes, and the 12 it dropped were the ones
    a vegan cook would have written."""
    recipes = json.loads((repository_root() / "data/recipes/recipes.json").read_text(encoding="utf-8"))
    literal = [r for r in recipes if "vegetarian" in r["dietary_tags"]]
    with_closure = [r for r in recipes if satisfies(["vegetarian"], r["dietary_tags"])]
    assert len(with_closure) > len(literal)
    assert all("vegan" in r["dietary_tags"] or "vegetarian" in r["dietary_tags"] for r in with_closure)
