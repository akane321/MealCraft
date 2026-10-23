"""Compare the supplied 119 recipe-role suggestions; never write reviewed tags."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.data import recipe_tags as current  # noqa: E402
from app.planning import vegetable_led as vegetables  # noqa: E402

OUT = ROOT / "data-engineering/docs/role-rules-119-20261023"


def baseline_module(base, path, name):
    source = subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=ROOT)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / path)
    sys.modules[name] = module
    exec(compile(source, str(ROOT / path), "exec"), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    old = baseline_module(args.base, "backend/app/data/recipe_tags.py", "app.data.task17_baseline")
    old_veg = baseline_module(args.base, "backend/app/planning/vegetable_led.py", "app.planning.task17_baseline")
    old.vegetable_led = old_veg.vegetable_led
    dishes = {d.key: d for d in current.curated_dishes() + current.release_dishes()}
    changes, by_id = [], {}
    for key, dish in sorted(dishes.items()):
        before, after = old.rule_tags(dish), current.rule_tags(dish)
        fields = {
            f: {"before": before.values[f], "after": after.values[f]}
            for f in current.CRITICAL_MODEL_FIELDS
            if before.values[f] != after.values[f]
        }
        before_allowed = (
            [before.values["meal_role"]]
            if before.values["meal_role"]
            else list(before.allowed_roles)
            if before.open
            else []
        )
        allowed = (
            [after.values["meal_role"]]
            if after.values["meal_role"]
            else list(after.allowed_roles)
            if after.open
            else []
        )
        lines = [(x.name, x.grams, x.text) for x in dish.lines]
        new_staple = current.homemade_staple(dish) and not old.homemade_staple(dish)
        rule_effects = []
        if new_staple:
            rule_effects.append(
                "dumplings"
                if re.search(r"\bdumplings?\b", dish.title, re.I)
                else "gnocchi"
                if re.search(r"\b(?:gnocchi|gnocches)\b", dish.title, re.I)
                else "staple_names"
            )
        if after.values["meal_role"] == "sauce" and before.values["meal_role"] != "sauce":
            rule_effects.append("dough_only_shells")
        if (
            current.PIZZA_TITLE.search(dish.title.lower())
            and after.values["meal_role"] == "one_bowl"
            and before.values["meal_role"] != "one_bowl"
        ):
            rule_effects.append("pizza_carrier")
        if vegetables.vegetable_led(lines) and not old_veg.vegetable_led(lines):
            rule_effects.append("tuber_vegetables")
        entry = {
            "id": key,
            "title": dish.title,
            "changes": fields,
            "rule_suggestion": after.values["meal_role"],
            "allowed_roles": allowed,
            "previous_allowed_roles": before_allowed,
            "effects": rule_effects,
            "incomplete_reason": after.incomplete_reason,
            "ingredients": [vars(line) for line in dish.lines],
        }
        by_id[key] = entry
        if fields or set(before_allowed) != set(allowed):
            changes.append(entry)
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        source = list(csv.DictReader(stream))
    assert len(source) == len({r["id"] for r in source}) == 119
    OUT.mkdir(exist_ok=True)
    # Retain only catalogue IDs/titles/role suggestions, not private reviewer notes.
    with (OUT / "119-source.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "title", "sheet_suggested_role"])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in source)
    comparisons = []
    for row in source:
        entry = by_id[row["id"]]
        assert row["title"] == entry["title"]
        wanted = row["sheet_suggested_role"]
        if wanted == "待组长定":
            status, reason = (
                "owner_bean_decision",
                "Whole-bean sides are not promoted to protein mains (owner decision).",
            )
        elif wanted in entry["allowed_roles"]:
            status, reason = (
                "target_allowed",
                "Actual ingredient evidence permits the requested review role; human review still required.",
            )
        elif entry["incomplete_reason"]:
            status, reason = "blocked", entry["incomplete_reason"]
        elif entry["rule_suggestion"]:
            status, reason = "different_role", "Evidence supports a different role, not the worksheet suggestion."
        else:
            status = "blocked"
            title = entry["title"].lower()
            recipe = dishes[row["id"]]
            lines = [(x.name, x.grams, x.text) for x in recipe.lines]
            non_tuber = old_veg.vegetable_share(lines)
            vegetable = vegetables.vegetable_share(lines)
            sugar = (recipe.sugar_g or 0) / recipe.carbohydrate_g if recipe.carbohydrate_g else None
            starch = current.staple_share(recipe, current.HOMEMADE_STARCH)
            reason = (
                "Souffle remains below the established vegetable/protein majority; thresholds unchanged."
                if "souffle" in title
                else "Fruit-led dishes do not meet the vegetable definition."
                if "watermelon" in title or "spareribs vegetarian" in title
                else "Stuffed/baked potatoes retain their previous classification."
                if any(t in title for t in ("kumpir", "taco baked", "pizza stuffed"))
                else "No qualifying starch evidence or protein/vegetable majority under the retained rules; "
                "inspect listed ingredients."
            )
            if wanted == "vegetable" and non_tuber is not None and vegetable is not None:
                reason += (
                    f" Non-tuber vegetables {non_tuber:.2%}; resulting vegetable share "
                    f"{vegetable:.2%} (needs 50%). Tubers need 40% non-tuber vegetables first."
                )
            if wanted == "staple":
                reason += f" Listed raw-starch share {starch:.2%} (needs 50%)."
                if sugar is not None and sugar >= 0.2:
                    reason += (
                        f" Sugar/carbohydrate {sugar:.2%} also exceeds the 20% ceiling (Yorkshire exception only)."
                    )
            if wanted == "protein_main":
                reason += (
                    " Eligible protein-side share after unchanged batter/starch exclusions: "
                    f"{current.protein_side_share(recipe):.2%} (needs 50%)."
                )
        comparisons.append(entry | {"target": wanted, "outcome": status, "reason": reason})
    effects = Counter(effect for row in changes for effect in row["effects"])
    outcomes = Counter(row["outcome"] for row in comparisons)
    packet = {
        "base": args.base,
        "seed": 20261023,
        "scope": "catalog and developer inputs only; no human tag acceptance",
        "effects": effects,
        "comparison_counts": outcomes,
        "comparisons": comparisons,
        "all_rule_suggestion_changes": changes,
        "human_sample": random.Random(20261023).sample(changes, min(30, len(changes))),
    }
    (OUT / "119-comparison.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [
        "# 119-recipe role review comparison",
        "",
        "Source: owner's second-edition worksheet, sheet 3. "
        "This compares review suggestions, not human gold labels or admitted recipes. "
        "The 422-model batch remains gated. Source revision is in the JSON metadata.",
        "",
        "## Counts",
        "",
        *[f"- {k}: {v}" for k, v in outcomes.items()],
        "",
        "## Rule effects (can overlap)",
        "",
        *[f"- {k}: {v}" for k, v in effects.items()],
        "",
    ]
    for outcome in outcomes:
        md += [f"## {outcome}", "", "| ID | Recipe | Target | Rule | Reason |", "|---|---|---|---|---|"]
        md += [
            f"| {r['id']} | {r['title'].replace('|', '/')} | {r['target']} | {r['rule_suggestion']} | {r['reason']} |"
            for r in comparisons
            if r["outcome"] == outcome
        ]
        md += [""]
    md += ["## All-catalog changed rule suggestions", "", "| ID | Recipe | Fields | Rules |", "|---|---|---|---|"]
    md += [
        f"| {r['id']} | {r['title'].replace('|', '/')} | `{json.dumps(r['changes'], ensure_ascii=False)}` | "
        f"{', '.join(r['effects'])} |"
        for r in changes
    ]
    md += ["", "## Fixed-seed sample: pending human review", ""]
    md += [f"- {r['id']} — {r['title']}" for r in packet["human_sample"]]
    (OUT / "119-comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"counts": outcomes, "effects": effects, "catalog_changes": len(changes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
