"""Task 16: rule-only impact and human-review suggestions, never a tag acceptance tool."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.data.recipe_tags import (  # noqa: E402
    CRITICAL_MODEL_FIELDS,
    curated_dishes,
    homemade_staple,
    line_sources,
    protein_side_share,
    release_dishes,
    rule_tags,
)
from app.data.release_v2 import release_dir  # noqa: E402
from app.data.tag_files import RECIPE_TAGS  # noqa: E402
from app.planning.meal_composition import meal_role_of  # noqa: E402
from app.planning.vegetable_led import (  # noqa: E402
    MEAT_SEASONING_SHARE,
    counted_weights,
    meat_or_fish,
    meat_share,
    vegetable_share,
)

OUT = ROOT / "data-engineering/docs/role-rules-20261022"
SEED = 20261022


def frozen(row):
    return any(
        row["estimated"].get(field, {}).get("method") == "llm" and not row["estimated"][field].get("reviewed")
        for field in CRITICAL_MODEL_FIELDS
    )


def compare_reports(base):
    """Only the four explicitly permitted developer diagnostics; never discover evaluation paths."""
    changes = []
    markdown = [
        "# Developer-report comparison",
        "",
        f"Base: `{base}`. No timing report was updated. "
        "These are developer regressions, not held-out capability or accuracy claims. "
        "The comparison uses archived base reports, not a newly run control baseline; changes cannot "
        "all be causally attributed to this rule repair when the archived reports predate other main changes.",
        "",
    ]
    for name in ("full-default", "shared-dish", "household-rules", "legacy-dev"):
        folder = "docs/evaluation" + (f"/{name}" if name != "legacy-dev" else "")
        path = f"{folder}/latest.json"
        # Legacy reports use platform newlines; normalise formatting before byte comparisons.
        for suffix in ("json", "md"):
            target = ROOT / folder / f"latest.{suffix}"
            target.write_text(target.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        raw = subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=ROOT)
        current = (ROOT / path).read_bytes()
        before, after = json.loads(raw), json.loads(current)
        assert after["passed"], name
        result = {
            "report": path,
            "changed": raw != current,
            "before_sha256": hashlib.sha256(raw).hexdigest(),
            "after_sha256": hashlib.sha256(current).hexdigest(),
            "cases": [],
        }
        markdown += [
            f"## {name}",
            "",
            f"Checks: {'PASS' if before['passed'] else 'FAIL'} → PASS. "
            f"JSON {'changed' if raw != current else 'byte-identical'}.",
            "",
        ]
        old_cases = {row["case"]: row for row in before.get("cases", [])}
        for row in after.get("cases", []):
            old = old_cases[row["case"]]
            was = old["runs"]["shared"] if name == "shared-dish" else old
            now = row["runs"]["shared"] if name == "shared-dish" else row
            metrics = {
                key: {"before": was.get("metrics", {}).get(key), "after": now.get("metrics", {}).get(key)}
                for key in sorted(was.get("metrics", {}).keys() | now.get("metrics", {}).keys())
                if was.get("metrics", {}).get(key) != now.get("metrics", {}).get(key)
            }
            old_recipes = {meal["recipe"] for meal in was.get("meals", [])}
            new_recipes = {meal["recipe"] for meal in now.get("meals", [])}
            case = {
                "case": row["case"],
                "changed": old != row,
                "metric_changes": metrics,
                "new_selected_titles": sorted(new_recipes - old_recipes),
                "removed_selected_titles": sorted(old_recipes - new_recipes),
            }
            result["cases"].append(case)
            markdown += [
                f"### {row['case']}",
                "",
                f"{'Changed' if old != row else 'Unchanged'}; checks {'PASS' if row['passed'] else 'FAIL'}.",
                "",
            ]
            if metrics:
                markdown += [
                    "| Metric | Before | After |",
                    "|---|---|---|",
                    *[
                        f"| {key} | {json.dumps(v['before'])} | {json.dumps(v['after'])} |"
                        for key, v in metrics.items()
                    ],
                    "",
                ]
            if old_recipes or new_recipes:
                markdown += [
                    f"New selected titles: {', '.join(case['new_selected_titles']) or 'none'}.",
                    "",
                    f"No longer selected: {', '.join(case['removed_selected_titles']) or 'none'}.",
                    "",
                ]
        changes.append(result)
    OUT.mkdir(exist_ok=True)
    (OUT / "report-comparison.json").write_text(
        json.dumps(changes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT / "report-comparison.md").write_text("\n".join(markdown).rstrip() + "\n", encoding="utf-8", newline="\n")
    print("Developer report comparison written; all four checks pass.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--reports-only", action="store_true")
    args = parser.parse_args()
    if args.reports_only:
        compare_reports(args.base)
        return
    before = json.loads(subprocess.check_output(["git", "show", f"{args.base}:{RECIPE_TAGS}"], cwd=ROOT))
    after = json.loads((ROOT / RECIPE_TAGS).read_text(encoding="utf-8"))
    assert before["llm_usage"] == after["llm_usage"]
    dishes = {d.key: d for d in curated_dishes() + release_dishes()}
    release_diets = {
        row["recipe_id"]: row["dietary_tags"]
        for line in (release_dir() / "recipes.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }
    suggestions, changed, frozen_rule_changes, beans, meat = [], [], [], [], []
    impacts = Counter()
    for key, dish in sorted(dishes.items()):
        old, new = before["recipes"][key], after["recipes"][key]
        proposal = rule_tags(dish)
        lines = [(line.name, line.grams, line.text) for line in dish.lines]
        veg, flesh = vegetable_share(lines), meat_share(lines)
        categories = {
            "homemade_staple": homemade_staple(dish),
            "meat_seasoned_vegetable": dish.course in {"side", "salad"}
            and veg is not None
            and veg >= 0.5
            and flesh is not None
            and 0 < flesh <= MEAT_SEASONING_SHARE,
            "protein_led_side": dish.course == "side"
            and protein_side_share(dish) >= 0.5
            and proposal.values["meal_role"] == "protein_main",
        }
        for field, provenance in old["estimated"].items():
            if provenance["method"] == "llm":
                assert new[field] == old[field] and new["estimated"][field] == provenance, (key, field)
        entry = {
            "id": key,
            "title": dish.title,
            "course": dish.course,
            "ingredients": [vars(line) for line in dish.lines],
            "rule_categories": categories,
        }
        if frozen(old):
            from types import SimpleNamespace

            assert meal_role_of(SimpleNamespace(**new)) is None
            changes = {
                field: {"before": old[field], "after": new[field]}
                for field, provenance in old["estimated"].items()
                if provenance["method"] == "rule" and old[field] != new[field]
            }
            if changes:
                frozen_rule_changes.append(entry | {"changes": changes, "review_status": "pending_liu_ub"})
            suggestions.append(
                entry
                | {
                    "stored": {f: new[f] for f in CRITICAL_MODEL_FIELDS},
                    "rule_suggestion": {f: proposal.values[f] for f in CRITICAL_MODEL_FIELDS},
                    "allowed_roles": [proposal.values["meal_role"]]
                    if proposal.values["meal_role"] is not None
                    else list(proposal.allowed_roles)
                    if "meal_role" in proposal.open
                    else [],
                    "incomplete_reason": proposal.incomplete_reason,
                    "review_status": "pending_liu_ub",
                }
            )
        elif old != new:
            changed.append(
                entry
                | {
                    "changes": {
                        f: {"before": old.get(f), "after": new.get(f)}
                        for f in sorted(old.keys() | new.keys())
                        if old.get(f) != new.get(f)
                    },
                    "review_status": "pending_human",
                }
            )
        if (
            dish.course in {"side", "salad"}
            and veg is not None
            and veg >= 0.5
            and any(meat_or_fish(x.name, x.text) for x in dish.lines)
        ):
            meat.append(
                entry
                | {
                    "vegetable_share": veg,
                    "meat_share": flesh,
                    "content_admitted": flesh is not None and flesh <= MEAT_SEASONING_SHARE,
                    "frozen": frozen(old),
                }
            )
        if homemade_staple(dish):
            impacts["homemade_staple_evidence"] += 1
        if dish.course == "side" and protein_side_share(dish) >= 0.5 and proposal.values["meal_role"] == "protein_main":
            impacts["protein_led_side_evidence"] += 1
        weights = counted_weights(lines)
        total = sum(weight for _, weight in weights)
        legume = sum(
            weight
            for line in dish.lines
            if "legume" in line_sources(line)
            for _, weight in counted_weights([(line.name, line.grams, line.text)])
        )
        if dish.course == "side" and total and legume / total >= 0.5:
            beans.append(
                entry
                | {
                    "legume_share": legume / total,
                    "stored_role": new["meal_role"],
                    "frozen": frozen(old),
                    "review_status": "owner_decision_pending",
                    "existing_dietary_tags": release_diets.get(key, []),
                }
            )
    bins = Counter(
        "unknown"
        if x["meat_share"] is None
        else next(
            label
            for upper, label in [
                (0.05, "(0,5%]"),
                (0.1, "(5,10%]"),
                (0.15, "(10,15%]"),
                (0.2, "(15,20%]"),
                (0.25, "(20,25%]"),
                (0.3, "(25,30%]"),
                (0.4, "(30,40%]"),
                (1, "(40,50%]"),
            ]
            if x["meat_share"] <= upper
        )
        for x in meat
    )
    impacts["new_vegetable_content_admissions"] = sum(x["content_admitted"] for x in meat)
    sample = random.Random(SEED).sample(changed, min(30, len(changed)))
    frozen_by_rule = {
        category: [row["id"] for row in suggestions if row["rule_categories"][category]]
        for category in ("homemade_staple", "meat_seasoned_vegetable", "protein_led_side")
    }
    payload = {
        "base": args.base,
        "seed": SEED,
        "scope": "release/curated ingredients only; no evaluation episodes",
        "frozen_model_values_provenance_and_usage_unchanged": True,
        "frozen_rule_owned_changes": frozen_rule_changes,
        "frozen_count": len(suggestions),
        "frozen_by_rule": frozen_by_rule,
        "frozen_rule_counts": {category: len(ids) for category, ids in frozen_by_rule.items()},
        "rule_evidence_counts": dict(impacts),
        "meat_cap": MEAT_SEASONING_SHARE,
        "meat_distribution": dict(bins),
        "vegetable_candidates": meat,
        "rule_owned_changes": changed,
        "human_sample": sample,
        "frozen_suggestions": suggestions,
        "deferred_bean_sides": beans,
        "liu_ub_109_ids": "not supplied; all frozen recipes covered, subset match pending",
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    md = [
        "# Role-rule review suggestions",
        "",
        "Generated with `data-engineering/scripts/role_rules_review.py`. "
        "No row is human-verified by this tool. Frozen model values and review flags are unchanged.",
        "",
        f"Baseline revision is recorded in review.json. Random sample seed: {SEED}. "
        f"Non-frozen rule-owned changes: {len(changed)}. "
        f"Rule-owned updates within the frozen batch: {len(frozen_rule_changes)}. "
        f"Frozen suggestions: {len(suggestions)}. Deferred bean sides: {len(beans)}.",
        "",
        "The specific 109 IDs have not been supplied; the complete frozen batch is included below. "
        "Do not interpret a suggested role or an allowed role as review/acceptance.",
        "",
        "## Rule-owned updates inside the frozen batch — liu-ub review required",
        "",
        "Only rule-owned fields update. Model values, their provenance/review flags and the gate remain unchanged; "
        "all these recipes are still excluded from planning. "
        "Egg allergens and diet restrictions still follow ingredients.",
        "",
        "| ID | Recipe | Rule-owned changes | Human review |",
        "|---|---|---|---|",
        *[
            f"| {row['id']} | {row['title']} | `{json.dumps(row['changes'], ensure_ascii=False)}` | pending liu-ub |"
            for row in frozen_rule_changes
        ],
        "",
        "## Frozen recipes reached by each new rule",
        "",
        "These are evidence/rule categories, not reviewed truth; missing-data reasons and the model freeze still bind.",
        "",
        "| Rule | Frozen recipes | IDs |",
        "|---|---:|---|",
        *[f"| {category} | {len(ids)} | {', '.join(ids)} |" for category, ids in frozen_by_rule.items()],
        "",
        "## Meat-share distribution (vegetable-led sides/salads containing flesh)",
        "",
        "| Counted flesh share | Recipes |",
        "|---|---:|",
        *[f"| {label} | {count} |" for label, count in sorted(bins.items())],
        "",
        "The 20% default is a conservative, interpretable boundary before the sparse 20–25% bin, "
        "not a statistically proved universal divide. Unknown quantities are excluded. "
        "See review.json for every newly admitted content candidate and its weighed evidence.",
        "",
        "## Newly content-admitted vegetable candidates",
        "",
        "This list describes the flesh-share gate only. Frozen tags, missing ingredients, course/role, "
        "member restrictions and other planning gates may still exclude a recipe.",
        "",
        "| ID | Recipe | Flesh share | Frozen |",
        "|---|---|---:|---|",
        *[
            f"| {r['id']} | {r['title']} | {100 * r['meat_share']:.2f}% | {r['frozen']} |"
            for r in meat
            if r["content_admitted"]
        ],
        "",
        "## Fixed-seed random sample — human confirmation required",
        "",
    ]
    for row in sample:
        md += [
            f"### {row['id']} — {row['title']}",
            "",
            f"Changes: `{json.dumps(row['changes'], ensure_ascii=False)}`",
            "",
            *[f"- {line['text'] or line['name']} — {line['grams']} g" for line in row["ingredients"]],
            "",
            "Human decision: pending.",
            "",
        ]
    md += [
        "## Deferred bean-led sides",
        "",
        "No promotion is authorised. Potential benefit is an extra "
        "legume main for vegetarian/vegan or flesh-excluding members, subject to actual diets, allergens, "
        "pricing and review. This is not a claim that any household's plan changes.",
        "",
        "The existing catalog diets indicate which member restrictions might benefit; they are "
        "not newly audited safety labels. Members with no diet restriction may gain alternatives too.",
        "",
        "| ID | Recipe | Current role | Frozen | Existing catalog diets |",
        "|---|---|---|---|---|",
    ]
    md += [
        f"| {r['id']} | {r['title']} | {r['stored_role']} | {r['frozen']} | {', '.join(r['existing_dietary_tags'])} |"
        for r in beans
    ]
    md += [
        "",
        "## Frozen batch — suggestions for liu-ub",
        "",
        "| ID | Recipe | Stored role | Rule suggestion | Allowed review roles |",
        "|---|---|---|---|---|",
    ]
    md += [
        f"| {r['id']} | {r['title']} | {r['stored']['meal_role']} | {r['rule_suggestion']['meal_role']} | "
        f"{', '.join(r['allowed_roles'])} |"
        for r in suggestions
    ]
    (OUT / "review.md").write_text("\n".join(md).rstrip() + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "impacts": dict(impacts),
                "changed": len(changed),
                "frozen": len(suggestions),
                "frozen_rule_owned_changes": len(frozen_rule_changes),
                "frozen_by_rule": {category: len(ids) for category, ids in frozen_by_rule.items()},
                "beans": len(beans),
                "distribution": dict(bins),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
