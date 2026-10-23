"""The human reviewer's table for the frozen model batch (owner 2026-10-23); never a tag acceptance tool.

For each frozen recipe it lists the stored value, the current rule's suggestion, the roles the model prompt offers
(unchanged) and the wider roles the human reviewer may choose (`recipe_tags.review_roles`). It marks rows whose rule
is newer than the batch, comparing three rule revisions: before ADR-0082 (`--pre-0082`), the base (`--base`, after
ADR-0085) and the working tree. It also counts the batch as consistent, grey, blocked or incomplete before and after.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.data import recipe_tags as current  # noqa: E402
from app.data.tag_files import RECIPE_TAGS  # noqa: E402

OUT = ROOT / "data-engineering/docs/role-rules-20261023b"
SEED = 20261023
RULES = "backend/app/data/recipe_tags.py"
VEGETABLES = "backend/app/planning/vegetable_led.py"


def rules_at(revision: str, name: str):
    """The tag rules of `revision`, run against that revision's vegetable rule, without touching the working tree."""

    def load(path, module_name):
        source = subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)
        module = types.ModuleType(module_name)
        module.__file__ = str(ROOT / path)
        sys.modules[module_name] = module  # dataclasses look their module up
        exec(compile(source, str(ROOT / path), "exec"), module.__dict__)
        return module

    live = sys.modules["app.planning.vegetable_led"]
    sys.modules["app.planning.vegetable_led"] = load(VEGETABLES, f"app.planning.vegetable_led_{name}")
    try:
        return load(RULES, f"app.data.recipe_tags_{name}")
    finally:
        sys.modules["app.planning.vegetable_led"] = live


def frozen(entry: dict) -> bool:
    return any(
        entry["estimated"].get(field, {}).get("method") == "llm" and not entry["estimated"][field].get("reviewed")
        for field in current.CRITICAL_MODEL_FIELDS
    )


def outcome(role, roles, incomplete, stored) -> str:
    if incomplete:
        return "incomplete"
    if role is not None:
        return "consistent" if role == stored else "blocked"
    return "grey" if stored in roles else "blocked"


def suggestion(tags) -> tuple:
    roles = list(tags.allowed_roles) if "meal_role" in tags.open else []
    return tags.values["meal_role"], roles, tags.values["protein_sources"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="revision whose rules (after ADR-0085) the table starts from")
    parser.add_argument("--pre-0082", default="3ef37e0", help="revision just before ADR-0082's rules")
    args = parser.parse_args()
    before, oldest = rules_at(args.base, "base"), rules_at(args.pre_0082, "pre_0082")
    entries = json.loads((ROOT / RECIPE_TAGS).read_text(encoding="utf-8"))["recipes"]
    dishes = current.curated_dishes() + current.release_dishes()
    rows, changes = [], []
    counts = {"before": Counter(), "after_rules": Counter(), "after_review_roles": Counter()}
    for dish in dishes:
        now, base, pre = current.rule_tags(dish), before.rule_tags(dish), oldest.rule_tags(dish)
        if suggestion(now) != suggestion(base):
            changes.append(
                {
                    "id": dish.key,
                    "title": dish.title,
                    "course": dish.course,
                    "before": dict(zip(("meal_role", "model_allowed_roles", "protein_sources"), suggestion(base))),
                    "after": dict(zip(("meal_role", "model_allowed_roles", "protein_sources"), suggestion(now))),
                    "frozen": frozen(entries[dish.key]),
                    "review_status": "pending_human",
                }
            )
        entry = entries[dish.key]
        if not frozen(entry):
            continue
        stored = entry["meal_role"]
        role, model_roles, _ = suggestion(now)
        review = current.review_roles(dish, now)
        newer = [
            label
            for label, changed in (
                ("ADR-0082/0085", suggestion(base)[:2] != suggestion(pre)[:2]),
                ("owner 2026-10-23", suggestion(now)[:2] != suggestion(base)[:2]),
            )
            if changed
        ]
        status = {
            "before": outcome(*suggestion(base)[:2], base.incomplete_reason, stored),
            "after_rules": outcome(role, model_roles, now.incomplete_reason, stored),
            "after_review_roles": outcome(role, review, now.incomplete_reason, stored),
        }
        for stage, value in status.items():
            counts[stage][value] += 1
        rows.append(
            {
                "id": dish.key,
                "title": dish.title,
                "course": dish.course,
                "stored": {field: entry[field] for field in current.CRITICAL_MODEL_FIELDS},
                "stored_method": entry["estimated"].get("meal_role", {}).get("method"),
                "rule_suggestion": {field: now.values[field] for field in current.CRITICAL_MODEL_FIELDS},
                "previous_rule_suggestion": base.values["meal_role"],
                "model_allowed_roles": [role] if role is not None else model_roles,
                "review_allowed_roles": review,
                "rule_newer_than_batch": newer,
                "status": status,
                "incomplete_reason": now.incomplete_reason,
                "ingredients": [vars(line) for line in dish.lines],
                "review_status": "pending_liu_ub",
            }
        )
    rows.sort(key=lambda row: row["id"])
    changes.sort(key=lambda row: row["id"])
    order = ("consistent", "grey", "blocked", "incomplete")
    packet = {
        "base": subprocess.check_output(["git", "rev-parse", args.base], cwd=ROOT, text=True).strip(),
        "pre_0082": subprocess.check_output(["git", "rev-parse", args.pre_0082], cwd=ROOT, text=True).strip(),
        "seed": SEED,
        "scope": "release/curated ingredients only; no evaluation episodes; no human acceptance",
        "model_allowed_roles_note": "the model prompt's roles; the reviewer's wider list never reaches the model",
        "frozen_counts": {stage: {key: counts[stage][key] for key in order} for stage in counts},
        "frozen_rows": rows,
        "catalog_rule_changes": changes,
        "human_sample": [row["id"] for row in random.Random(SEED).sample(changes, min(30, len(changes)))],
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "review.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    stages = {
        "before": "Before (base rules, model options)",
        "after_rules": "After: these rules, model options",
        "after_review_roles": "After: these rules, reviewer options",
    }

    def cell(text) -> str:
        return str(text).replace("|", "/")

    md = [
        "# Reviewer table for the frozen model batch",
        "",
        "Generated with `data-engineering/scripts/role_review_table.py`. No row is human-verified by this tool; "
        "frozen model values, their provenance and the gate are unchanged. Revisions are in review.json.",
        "",
        "## Frozen batch counts",
        "",
        "Consistent: the rule names the stored role. Grey: the rule leaves the role open and the stored role is "
        "allowed. Blocked: the rule names another role, or the stored role is not allowed. Incomplete: a missing "
        "ingredient line closes the row.",
        "",
        "| Stage | Consistent | Grey | Blocked | Incomplete |",
        "|---|---:|---:|---:|---:|",
        *[f"| {label} | " + " | ".join(str(counts[stage][key]) for key in order) + " |" for stage, label in stages.items()],
        "",
        "## Frozen batch: suggestions for liu-ub",
        "",
        "Reviewer roles add `staple` and `one_bowl` when the rule's staple share is 0 (owner 2026-10-23); the "
        "model prompt's roles are unchanged. 'Rule newer' names the rule revision that changed this row's "
        "suggestion after the batch was labelled: disagreement there is not a model error by itself.",
        "",
        "| ID | Recipe | Stored role | Rule suggestion | Reviewer roles | Before → after | Rule newer |",
        "|---|---|---|---|---|---|---|",
        *[
            f"| {row['id']} | {cell(row['title'])} | {row['stored']['meal_role']} | "
            f"{row['rule_suggestion']['meal_role']} | {', '.join(row['review_allowed_roles'])} | "
            f"{row['status']['before']} → {row['status']['after_review_roles']} | "
            f"{', '.join(row['rule_newer_than_batch'])} |"
            for row in rows
        ],
        "",
        "## Every catalog rule change against the base",
        "",
        "Rule-owned changes refresh the tag file; frozen rows keep their model values. Pending human review.",
        "",
        "| ID | Recipe | Course | Role before → after | Model options after | Frozen |",
        "|---|---|---|---|---|---|",
        *[
            f"| {row['id']} | {cell(row['title'])} | {row['course']} | {row['before']['meal_role']} → "
            f"{row['after']['meal_role']} | {', '.join(row['after']['model_allowed_roles'])} | {row['frozen']} |"
            for row in changes
        ],
        "",
        f"## Fixed-seed sample of the changes (seed {SEED}): pending human review",
        "",
        *[f"- {key}" for key in packet["human_sample"]],
    ]
    (OUT / "review.md").write_text("\n".join(md).rstrip() + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"frozen_counts": packet["frozen_counts"], "catalog_changes": len(changes)}))


if __name__ == "__main__":
    main()
