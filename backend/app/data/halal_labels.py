"""Generate `data/ingredients/halal-labels-v1.json` and its review queue (docs/design/halal.md; ADR-0104).

    uv run --project backend python -m app.data.halal_labels      # from the repository root, offline, deterministic

One label per catalog ingredient: the release v2.2 ingredients plus the curated ones. The first rule that applies
decides, so a reviewer can audit by `source`:

1. `rule:pork`: the pork family of the ingredient hierarchy (pork and all that is a variety of, or made from, it).
2. `rule:alcohol`: `group:alcohol` of the hierarchy, and what is made from it.
3. `rule:doubtful`: sources a label cannot settle (`DOUBTFUL`, extracts and flavourings of unstated ethanol).
4. `rule:may_contain`: a `may_contain` link to pork, alcohol or something already uncertain; `uncertain`.
5. `rule:meat`: meat, poultry and what is made from them, or any other flesh that is not fish or seafood;
   `halal` with `needs_certification`. Also an item with a `may_contain` link to meat (ramen, stuffing mix: flavour
   packets); no pork, alcohol or doubt reached it first.
6. `rule:food_group`: everything else (plants, fish and seafood, eggs, dairy, grains ...) is `halal`.

A person's corrections live in `halal-overrides-v1.json` and are applied when the labels are read, not here.
The review queue lists every `uncertain` and `needs_certification` label, the `halal` labels a person should check
(`CHECK_TOKENS`) and a fixed-seed sample of the other `halal` ones. The second-round queue `halal-review-v2.csv`
lists the other `halal` labels of `SECOND_ROUND_GROUPS`. Their reviewed copies are `VERDICTS_FILES`: a label the
person could not settle without the product's formula or certification is overridden to need a certified product
(owner, 2026-10-31), as meat does.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter

from app.core.paths import data_root
from app.data.halal import LABELS_FILE
from app.data.ingredient_hierarchy import GROUP_PREFIX, Hierarchy, read_links
from app.data.release_v2 import normalized_name, release_dir

REVIEW_FILE = "ingredients/halal-review-v1.csv"
# The queues as the person returned them (2026-10-31): the first, the second round, and the processed grains and
# flavourings the reviewer screened besides. Every verdict short of `ok` is an override that needs a certified product.
VERDICTS_FILE = "ingredients/halal-review-v1-verdicts.csv"
VERDICTS_FILES = (
    VERDICTS_FILE,
    "ingredients/halal-review-v2-verdicts.csv",
    "ingredients/halal-review-additional-verdicts.csv",
)
SAMPLE_SIZE = 60
SAMPLE_SEED = 20261029

PORK_ROOT = "pork"
ALCOHOL_ROOT = "group:alcohol"
PRODUCED = ("same", "variety", "made_from")
# What the planner treats as meat; anything below them (broth, gravy, cuts) is meat too.
MEAT_ROOTS = ("meat", "beef", "chicken", "turkey", "duck", "lamb", "goat", "rabbit", "venison", "cornish_hen")
# Flesh that is fish or seafood, or a condiment made from it: halal as plants are (no slaughter rule).
SEAFOOD = frozenset(
    "anchovy bonito_flakes catfish clam clam_juice cod crab dashi fish_broth fish_cake fish_fillet fish_oil fish_sauce"
    " hake halibut imitation_crab lobster milkfish mussel nuoc_cham octopus oyster oyster_sauce red_snapper salmon"
    " salt_cod sardine scallop seafood_mix shrimp shrimp_paste smoked_haddock squid squid_broth steak_sauce swordfish"
    " trout tuna worcestershire".split()
)
# Source or process a label cannot settle; unknown counts as not halal.
DOUBTFUL = {
    "gelatin": "gelatin of unstated source (pork, beef or fish)",
    "bouillon": "stock cube or powder of unstated source",
    "crickets": "edible insects: species, processing and other ingredients unverified (MUIS allows qualifying ones)",
    "mincemeat": "fruit mince made with suet and often brandy",
    "tapai": "fermented rice: the product and its ruling unverified (fermentation alone is not the doubt)",
    "shortening": "shortening may be made with lard",
    "shortening_or_oil": "shortening may be made with lard",
    "vanilla": "the bare name does not say vanilla bean, extract or flavouring",
    "pandan_extract": "water extract or compound flavouring not told apart",
}
# Ethanol as a solvent: MUIS allows a non-khamr source within limits, and the catalog states neither (review 10-31).
DOUBTFUL_TOKENS = ("extract", "flavoring")
# Labelled halal, but schools or products differ: listed for a person in the review queue's `check` rows.
CHECK_TOKENS = {
    "cheese": "cheese may be made with animal rennet",
    "wine": "wine vinegar: schools differ",
    "sherry": "sherry vinegar: schools differ",
}
# The first review (10-31) found most sampled condiments and prepared foods undetermined without a formula, so every
# other `halal` label of these food groups goes to a second round (`REVIEW_V2_FILE`); the labels stand until then.
SECOND_ROUND_GROUPS = ("condiment", "prepared")
REVIEW_V2_FILE = "ingredients/halal-review-v2.csv"

FIELDS = ("normalized_name", "status", "needs_certification", "source", "reason")


def _label(name: str, status: str, source: str, reason: str, needs_certification: bool = False) -> dict:
    return {
        "normalized_name": name,
        "status": status,
        "needs_certification": needs_certification,
        "source": source,
        "reason": reason,
    }


def catalog() -> dict[str, tuple[str | None, str | None]]:
    """normalized_name -> (food_group, dietary_origin); curated-only ingredients have neither."""
    names: dict[str, tuple[str | None, str | None]] = {}
    for line in (release_dir() / "ingredients.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            names[normalized_name(record["ingredient_id"])] = (record["food_group"], record["dietary_origin"])
    for record in json.loads((data_root() / "ingredients/ingredients.json").read_text(encoding="utf-8")):
        names.setdefault(record["normalized_name"], (None, None))
    return names


def _doubtful(name: str) -> str | None:
    if name in DOUBTFUL:
        return DOUBTFUL[name]
    if any(token in name.split("_") for token in DOUBTFUL_TOKENS):
        return "extract or flavouring: the ethanol's source and amount unstated"
    return None


def labels(names: dict[str, tuple[str | None, str | None]], hierarchy: Hierarchy) -> list[dict]:
    pork = hierarchy.expand([PORK_ROOT], PRODUCED)
    alcohol = hierarchy.expand([ALCOHOL_ROOT], PRODUCED) - {ALCOHOL_ROOT}
    meat = hierarchy.expand(MEAT_ROOTS, (*PRODUCED, "either_of"))
    result: dict[str, dict] = {}

    def decide(name: str) -> dict:
        if name in result:
            return result[name]
        result[name] = _label(name, "uncertain", "rule:doubtful", "being decided")  # a cycle stays uncertain
        food_group, origin = names[name]
        parents = hierarchy.entries.get(name, {}).get("parents", [])
        if name in pork:
            label = _label(name, "not_halal", "rule:pork", "pork or made from pork")
        elif name in alcohol:
            label = _label(name, "not_halal", "rule:alcohol", "alcohol, or made from alcohol")
        elif (why := _doubtful(name)) is not None:
            label = _label(name, "uncertain", "rule:doubtful", why)
        elif linked := [
            parent["id"]
            for parent in parents
            if (parent["relation"] == "may_contain" and (parent["id"] in pork | alcohol | {ALCOHOL_ROOT}))
            or (
                not parent["id"].startswith(GROUP_PREFIX)
                and parent["id"] in names
                and parent["relation"] in (*PRODUCED, "may_contain")
                and decide(parent["id"])["status"] == "uncertain"
            )
        ]:
            label = _label(name, "uncertain", "rule:may_contain", f"may contain or be made from {', '.join(linked)}")
        elif name in meat or (origin == "flesh" and name not in SEAFOOD):
            label = _label(name, "halal", "rule:meat", "meat or poultry: halal only from a certified product", True)
        elif meat_linked := [p["id"] for p in parents if p["relation"] == "may_contain" and p["id"] in meat]:
            why = f"may contain {', '.join(meat_linked)} (flavour packet): halal only as a product marked Halal"
            label = _label(name, "halal", "rule:meat", why, True)
        else:
            label = _label(name, "halal", "rule:food_group", f"{food_group or 'whole food'}, no pork or alcohol")
        result[name] = label
        return label

    return [decide(name) for name in sorted(names)]


def _check(item: dict) -> str:
    """Why a person should look at this `halal` label in particular; the label stands until they decide."""
    if item["status"] != "halal" or item["needs_certification"]:
        return ""
    return next((note for token, note in CHECK_TOKENS.items() if token in item["normalized_name"].split("_")), "")


def review_rows(items: list[dict]) -> list[dict]:
    queue = [("uncertain", i, "") for i in items if i["status"] == "uncertain"]
    queue += [("needs_certification", i, "") for i in items if i["needs_certification"]]
    queue += [("check", i, _check(i)) for i in items if _check(i)]
    plain = [i for i in items if i["status"] == "halal" and not i["needs_certification"] and not _check(i)]
    sample = sorted(random.Random(SAMPLE_SEED).sample(plain, SAMPLE_SIZE), key=_name)
    queue += [("sample", i, "") for i in sample]
    return [{"queue": q, **i, "verdict": "", "note": note} for q, i, note in queue]


def second_round_rows(items: list[dict], names: dict[str, tuple[str | None, str | None]]) -> list[dict]:
    """The `halal` labels of `SECOND_ROUND_GROUPS` that the first queue did not hold."""
    first = {row["normalized_name"] for row in review_rows(items)}
    return [
        {"queue": "second_round", **i, "verdict": "", "note": ""}
        for i in items
        if i["source"] == "rule:food_group"
        and names[i["normalized_name"]][0] in SECOND_ROUND_GROUPS
        and i["normalized_name"] not in first
    ]


def _name(item: dict) -> str:
    return item["normalized_name"]


def write(items: list[dict], names: dict[str, tuple[str | None, str | None]]) -> None:
    root = data_root()
    lines = ",\n".join("  " + json.dumps(item, ensure_ascii=False) for item in items)
    (root / LABELS_FILE).write_text(
        '{\n "schema_version": "halal-labels-v1",\n "items": [\n' + lines + "\n ]\n}\n", encoding="utf-8"
    )
    for name, rows in ((REVIEW_FILE, review_rows(items)), (REVIEW_V2_FILE, second_round_rows(items, names))):
        with (root / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, ["queue", *FIELDS, "verdict", "note"], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    names = catalog()
    items = labels(names, read_links())
    write(items, names)
    by_status = Counter((i["status"] + (" +cert" if i["needs_certification"] else "")) for i in items)
    print(f"{len(items)} labels")
    for title, counter in (("status", by_status), ("source", Counter(i["source"] for i in items))):
        print(f"by {title}: " + ", ".join(f"{key} {count}" for key, count in sorted(counter.items())))


if __name__ == "__main__":
    main()
