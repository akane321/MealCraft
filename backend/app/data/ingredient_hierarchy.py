"""What each ingredient belongs to, so that excluding one excludes everything that is it.

The planner matches an exclusion to a recipe's ingredient ids exactly. The catalog
holds the same food under several ids (the curated `firm_tofu` and release v2.1's
`tofu`), foods made from another (`bacon` from `pork`) and families with no single
id at all (alcohol). Without this table "no pork" leaves bacon in the plan.

The contract is `docs/design/ingredient-hierarchy.md`; this module is its only
reader. It uses the standard library only, so `scripts/check_ingredient_hierarchy.py`
can run it without a container or installed dependencies.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from app.core.paths import find_repository_root

SCHEMA_VERSION = "ingredient-hierarchy-v1"
RELATIONS = ("same", "variety", "made_from", "either_of", "may_contain")
GROUP_PREFIX = "group:"
MIN_REASON = 20
# A reason written more often than this is a template, not a judgement about one ingredient.
MAX_REASON_REPEATS = 3

# Who decides each ingredient. Release v2.1 ids go by the food group the release gives
# them; the curated catalog's own ids (those release v2.1 does not share) go to WP1.
PACKAGES = {
    "WP1": "curated-only",
    "WP2": frozenset({"protein", "dairy", "fat", "beverage", "prepared", "condiment"}),
    "WP3": frozenset(
        {
            "vegetable",
            "grain",
            "seasoning",
            "fruit",
            "flavoring",
            "herb",
            "sweetener",
            "leavening",
            "plant_milk",
            "liquid",
        }
    ),
}
# Groups live in their own file so any package can point at one before the others merge.
GROUPS_FILE = "groups.json"
FILES = {
    "WP1": "wp1-curated.json",
    "WP2": "wp2-animal-drink-prepared.json",
    "WP3": "wp3-plant-pantry.json",
}


def _root() -> Path:
    # Found by the committed catalog, not by counting parents: the file sits at a
    # different depth in a checkout and in the container.
    return find_repository_root(Path(__file__).parent)


@dataclass(frozen=True)
class Ingredient:
    id: str
    name: str
    food_group: str | None
    package: str
    occurrences: int


@dataclass
class Hierarchy:
    ingredients: dict[str, Ingredient]
    groups: dict[str, dict]
    entries: dict[str, dict]
    entry_package: dict[str, str]
    errors: list[str] = field(default_factory=list)

    # ----- expansion -----

    def children(self) -> dict[str, set[str]]:
        down: dict[str, set[str]] = defaultdict(set)
        for child, entry in self.entries.items():
            for parent in entry.get("parents", []):
                down[parent["id"]].add(child)
                if parent["relation"] == "same":
                    down[child].add(parent["id"])  # the same food, whichever id the user named
        return down

    def expand(self, excluded: Iterable[str]) -> set[str]:
        """Everything excluding these ids excludes: themselves and all that belong to them.

        It never climbs: excluding `cherry_tomato` does not exclude `tomato`. Only a
        `same` link is followed both ways, because it is one food under two ids.
        """
        down = self.children()
        seen: set[str] = set()
        stack = list(excluded)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(down.get(current, ()))
        return seen

    def ancestors(self, ingredient_id: str) -> set[str]:
        up: dict[str, set[str]] = defaultdict(set)
        for child, entry in self.entries.items():
            for parent in entry.get("parents", []):
                up[child].add(parent["id"])
                if parent["relation"] == "same":
                    up[parent["id"]].add(child)
        seen: set[str] = set()
        stack = list(up.get(ingredient_id, ()))
        while stack:
            current = stack.pop()
            if current in seen or current == ingredient_id:
                continue
            seen.add(current)
            stack.extend(up.get(current, ()))
        return seen

    # ----- coverage -----

    def owned(self, package: str) -> list[str]:
        return sorted(i.id for i in self.ingredients.values() if i.package == package)

    def undecided(self, package: str) -> list[str]:
        return [i for i in self.owned(package) if i not in self.entries]


def look_alikes(ingredient_id: str, known: Iterable[str]) -> list[str]:
    """Other ids spelled inside this one as whole words: `almond_milk` holds `almond` and `milk`.

    Each must be decided -- a parent, or named in `not_parents` -- because the name
    alone is wrong about half the time (`almond_milk` is not milk, `bacon_grease` is bacon).
    """
    padded = f"_{ingredient_id}_"
    return sorted(other for other in known if other != ingredient_id and f"_{other}_" in padded)


def _load_vocabulary(root: Path) -> dict[str, Ingredient]:
    occurrences: Counter[str] = Counter()
    release_recipes = root / "data-engineering/data/release/v2.1/recipes.jsonl"
    for line in release_recipes.read_text(encoding="utf-8").splitlines():
        if line.strip():
            recipe = json.loads(line)
            occurrences.update({row["canonical_ingredient_id"][4:].lower() for row in recipe["ingredients"]})
    ingredients: dict[str, Ingredient] = {}
    release = root / "data-engineering/data/release/v2.1/ingredients.jsonl"
    for line in release.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ingredient_id = row["ingredient_id"][4:].lower()
        package = next(p for p, groups in PACKAGES.items() if p != "WP1" and row["food_group"] in groups)
        ingredients[ingredient_id] = Ingredient(
            ingredient_id, row["canonical_name"], row["food_group"], package, occurrences[ingredient_id]
        )
    curated_uses: Counter[str] = Counter()
    for recipe in json.loads((root / "data/recipes/recipes.json").read_text(encoding="utf-8")):
        curated_uses.update({row["ingredient"] for row in recipe["ingredients"]})
    for row in json.loads((root / "data/ingredients/ingredients.json").read_text(encoding="utf-8")):
        name = row["normalized_name"]
        if name not in ingredients:
            ingredients[name] = Ingredient(name, row["display_name"], None, "WP1", curated_uses[name])
    return ingredients


def load(root: Path | None = None) -> Hierarchy:
    """Read and check every package file. Errors are collected, never raised."""
    root = root or _root()
    ingredients = _load_vocabulary(root)
    hierarchy = Hierarchy(ingredients=ingredients, groups={}, entries={}, entry_package={})
    errors = hierarchy.errors
    files = {package: root / "data/ingredients/hierarchy" / name for package, name in FILES.items()}

    groups_path = root / "data/ingredients/hierarchy" / GROUPS_FILE
    if not groups_path.exists():
        errors.append(f"{GROUPS_FILE}: missing")
    else:
        groups_document = json.loads(groups_path.read_text(encoding="utf-8"))
        if groups_document.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{GROUPS_FILE}: schema_version must be {SCHEMA_VERSION}")
        for group_id, group in (groups_document.get("groups") or {}).items():
            if not re.fullmatch(r"group:[a-z0-9_]+", group_id):
                errors.append(f"{GROUPS_FILE}: group id {group_id!r} must look like group:snake_case")
            if len((group.get("description") or "").strip()) < MIN_REASON:
                errors.append(f"{GROUPS_FILE}: group {group_id} needs a description")
            if not (group.get("serves") or "").strip():
                errors.append(f"{GROUPS_FILE}: group {group_id} needs `serves`, the household sentence it exists for")
            hierarchy.groups[group_id] = group

    documents = {}
    for package, path in files.items():
        if not path.exists():
            errors.append(f"{path.name}: missing")
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        documents[package] = document
        if document.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{path.name}: schema_version must be {SCHEMA_VERSION}")
        if document.get("package") != package:
            errors.append(f"{path.name}: package must be {package}")
        if "groups" in document:
            errors.append(f"{path.name}: groups are declared in {GROUPS_FILE}, not in a package file")
        for ingredient_id, entry in (document.get("entries") or {}).items():
            if ingredient_id in hierarchy.entries:
                errors.append(f"{path.name}: {ingredient_id} is decided in two files")
                continue
            hierarchy.entries[ingredient_id] = entry
            hierarchy.entry_package[ingredient_id] = package

    known = set(ingredients) | set(hierarchy.groups)
    reasons: Counter[str] = Counter()
    for ingredient_id, entry in hierarchy.entries.items():
        where = f"{FILES[hierarchy.entry_package[ingredient_id]]}: {ingredient_id}"
        if ingredient_id not in ingredients:
            errors.append(f"{where}: not an ingredient id in the catalog")
            continue
        owner = ingredients[ingredient_id].package
        if owner != hierarchy.entry_package[ingredient_id]:
            errors.append(f"{where}: belongs to {owner}, decide it in {FILES[owner]}")
        reason = (entry.get("reason") or "").strip()
        if len(reason) < MIN_REASON:
            errors.append(f"{where}: reason must say what it is and why, in at least {MIN_REASON} characters")
        reasons[reason.lower()] += 1
        parents = entry.get("parents")
        if not isinstance(parents, list):
            errors.append(f"{where}: parents must be a list, [] when it belongs to nothing")
            continue
        seen_parents = set()
        for parent in parents:
            parent_id, relation = parent.get("id"), parent.get("relation")
            if parent_id not in known:
                errors.append(f"{where}: parent {parent_id!r} is neither an ingredient id nor a declared group")
            if parent_id == ingredient_id:
                errors.append(f"{where}: cannot be its own parent")
            if relation not in RELATIONS:
                errors.append(f"{where}: relation {relation!r} must be one of {', '.join(RELATIONS)}")
            if relation == "same" and str(parent_id).startswith(GROUP_PREFIX):
                errors.append(f"{where}: an ingredient cannot be the same as a group")
            if parent_id in seen_parents:
                errors.append(f"{where}: parent {parent_id} listed twice")
            seen_parents.add(parent_id)
        same = [p for p in parents if p.get("relation") == "same"]
        if len(same) > 1:
            errors.append(f"{where}: a food has one other name at most; `same` points to one canonical id")
        not_parents = entry.get("not_parents", [])
        if not isinstance(not_parents, list) or any(item not in known for item in not_parents):
            errors.append(f"{where}: not_parents must list known ids")
            not_parents = []
        if set(not_parents) & seen_parents:
            errors.append(f"{where}: an id cannot be both a parent and a not_parent")

    for ingredient_id, entry in hierarchy.entries.items():
        for parent in entry.get("parents", []):
            if parent.get("relation") == "same":
                target = hierarchy.entries.get(parent["id"], {})
                if any(p.get("relation") == "same" for p in target.get("parents", [])):
                    errors.append(f"{ingredient_id}: `same` must point at the canonical id, not at another alias")

    for reason, count in reasons.items():
        if reason and count > MAX_REASON_REPEATS:
            errors.append(f"the reason {reason[:60]!r} is used {count} times; write each ingredient's own reason")

    _check_cycles(hierarchy)
    for ingredient_id, entry in hierarchy.entries.items():
        if ingredient_id not in ingredients or not isinstance(entry.get("parents"), list):
            continue
        decided = hierarchy.ancestors(ingredient_id) | set(entry.get("not_parents", []))
        for other in look_alikes(ingredient_id, ingredients):
            if other not in decided:
                errors.append(
                    f"{ingredient_id}: its name contains {other!r}; make it a parent or list it in not_parents"
                )
    return hierarchy


def empty_groups(hierarchy: Hierarchy) -> list[str]:
    """Groups nothing belongs to yet: normal while the packages are open, an error once they close."""
    used = {p["id"] for e in hierarchy.entries.values() for p in e.get("parents", [])}
    return sorted(set(hierarchy.groups) - used)


def _check_cycles(hierarchy: Hierarchy) -> None:
    up = {
        child: [p["id"] for p in entry.get("parents", []) if p.get("relation") != "same"]
        for child, entry in hierarchy.entries.items()
        if isinstance(entry.get("parents"), list)
    }
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            hierarchy.errors.append("cycle: " + " -> ".join([*path[path.index(node) :], node]))
            return
        state[node] = 1
        for parent in up.get(node, []):
            visit(parent, [*path, node])
        state[node] = 2

    for node in up:
        visit(node, [])


def read_links(root: Path | None = None) -> Hierarchy:
    """Only the links, unchecked: what the product needs at run time.

    It reads the four hierarchy files and nothing else, so it works wherever
    `data/` is mounted. CI runs the full `load()` on every change, so the links it
    reads have already passed every rule.
    """
    directory = (root or _root()) / "data/ingredients/hierarchy"
    hierarchy = Hierarchy(ingredients={}, groups={}, entries={}, entry_package={})
    groups_path = directory / GROUPS_FILE
    if groups_path.exists():
        hierarchy.groups = json.loads(groups_path.read_text(encoding="utf-8")).get("groups") or {}
    for package, name in FILES.items():
        path = directory / name
        if not path.exists():
            continue
        for ingredient_id, entry in (json.loads(path.read_text(encoding="utf-8")).get("entries") or {}).items():
            hierarchy.entries[ingredient_id] = entry
            hierarchy.entry_package[ingredient_id] = package
    return hierarchy


@cache
def runtime() -> Hierarchy:
    return read_links()


def expand_exclusions(excluded: Iterable[str]) -> list[str]:
    """A household's exclusions with everything that belongs to them, for the planner to match exactly."""
    return sorted(runtime().expand(excluded))


if __name__ == "__main__":
    loaded = load()  # the full check; scripts/check_ingredient_hierarchy.py is the author-facing version
    print("\n".join(loaded.errors) or "ok")
    for name in FILES:
        print(f"{name}: {len(loaded.owned(name)) - len(loaded.undecided(name))}/{len(loaded.owned(name))} decided")
