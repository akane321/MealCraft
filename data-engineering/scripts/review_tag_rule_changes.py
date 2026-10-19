"""Create a separate, reproducible owner review of changed tags; never rewrite the original audit."""

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

from app.data.recipe_tags import CRITICAL_MODEL_FIELDS, curated_dishes, release_dishes, rule_tags  # noqa: E402
from app.data.tag_files import RECIPE_TAG_FIELDS, RECIPE_TAGS  # noqa: E402

OUT = ROOT / "data-engineering/docs/recipe-tags-v1-rule-changes-review"
KNOWN_CASES = {
    "RCP2_CB88A5A0DF4C",
    "RCP2_1C43BC6CC166",
    "RCP2_1BBDFA22270A",
    "RCP2_546DFF631ED4",
    "RCP2_CB386B8363E1",
    "RCP2_491808DE2CEB",
    "RCP2_19650787C340",
    "RCP2_B2843B21CE46",
    "RCP2_E3B3B3009341",
}


def gated(entries: dict) -> set[str]:
    return {
        key
        for key, row in entries.items()
        if any(
            row.get("estimated", {}).get(field, {}).get("method") == "llm"
            and not row["estimated"][field].get("reviewed")
            for field in CRITICAL_MODEL_FIELDS
        )
    }


def choose(keys: list[str], count: int, seed: int) -> list[str]:
    """Known regressions plus a seeded random remainder, explicitly not a population-accuracy sample."""
    ordered = sorted(keys)
    chosen = sorted(set(ordered) & KNOWN_CASES)[:count]
    rest = [key for key in ordered if key not in chosen]
    return chosen + random.Random(seed).sample(rest, min(count - len(chosen), len(rest)))


def compare_default(base: str) -> None:
    """Compare only the explicitly permitted developer report, never other evaluation outputs."""
    relative = "docs/evaluation/full-default/latest.json"
    old = json.loads(subprocess.check_output(["git", "-C", str(ROOT), "show", f"{base}:{relative}"]))
    after_bytes = (ROOT / relative).read_bytes()
    new = json.loads(after_bytes)
    old_cases = {row["case"]: row for row in old["cases"]}
    assert new["passed"] and all(row["passed"] for row in new["cases"])
    changes = []
    for row in new["cases"]:
        before = old_cases[row["case"]]
        metrics = {
            key: {"before": before["metrics"].get(key), "after": row["metrics"].get(key)}
            for key in sorted(before["metrics"].keys() | row["metrics"].keys())
            if before["metrics"].get(key) != row["metrics"].get(key)
        }
        was = {(m["day"], m["meal"], m["role"]): m for m in before["meals"]}
        now = {(m["day"], m["meal"], m["role"]): m for m in row["meals"]}
        substitutions = [
            {"slot": list(key), "before": was.get(key), "after": now.get(key)}
            for key in sorted(was.keys() | now.keys())
            if was.get(key) != now.get(key)
        ]
        changes.append(
            {
                "case": row["case"],
                "passed_before": before["passed"],
                "passed_after": row["passed"],
                "metric_changes": metrics,
                "meal_changes": substitutions,
            }
        )
    selected = [meal["recipe"] for row in new["cases"] for meal in row["meals"]]
    from app.data.recipe_tags import component

    assert all(not component(title, "main") for title in selected), "A standalone component still appears in a plan."
    payload = {
        "base_commit": base,
        "new_report_sha256": hashlib.sha256(after_bytes).hexdigest(),
        "scope": "developer full-default only; not capability evaluation or a speed acceptance",
        "component_title_check": "no selected title is a standalone filling/topping component",
        "cases": changes,
    }
    folder = ROOT / "docs/evaluation/full-default"
    (folder / "rule-change-comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Rule-change comparison: full default",
        "",
        "Generated from the pre-fix and current developer-only `latest.json`. All cases still pass. "
        "This is a regression comparison, not a complete label-accuracy or speed claim. "
        "Original model fields remain gated. The timing artifact records the run's base HEAD; "
        "the run used the uncommitted rule fixes in this PR, not an unmodified base checkout.",
        "",
        "No selected recipe title is a standalone filling/topping component. "
        "Component classification, not an unrestricted search for the word 'filling', is tested.",
        "",
    ]
    for row in changes:
        lines += [
            f"## {row['case']}",
            "",
            "Checks: PASS → PASS.",
            "",
            "| Changed metric | Before | After |",
            "|---|---|---|",
        ]
        for key, values in row["metric_changes"].items():
            lines.append(
                f"| {key} | {json.dumps(values['before'], ensure_ascii=False)} | "
                f"{json.dumps(values['after'], ensure_ascii=False)} |"
            )
        lines += ["", "| Day / meal / role | Before | After |", "|---|---|---|"]
        for item in row["meal_changes"]:
            before, after = item["before"], item["after"]
            old_text = f"{before['recipe']} ({before['servings']} portions)" if before else "—"
            new_text = f"{after['recipe']} ({after['servings']} portions)" if after else "—"
            lines.append(f"| {' / '.join(map(str, item['slot']))} | {old_text} | {new_text} |")
        lines.append("")
    (folder / "rule-change-comparison.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--count", type=int, default=25, choices=range(20, 31))
    parser.add_argument("--seed", type=int, default=20261019)
    args = parser.parse_args()
    if OUT.with_suffix(".json").exists():
        prior = json.loads(OUT.with_suffix(".json").read_text(encoding="utf-8"))
        assert not any(value not in (None, "") for row in prior["records"] for value in row["verdict"].values()), (
            "Do not overwrite an owner-reviewed changed-case packet."
        )
    base = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", args.base_ref], text=True).strip()
    old = json.loads(subprocess.check_output(["git", "-C", str(ROOT), "show", f"{base}:{RECIPE_TAGS}"]))["recipes"]
    current_bytes = (ROOT / RECIPE_TAGS).read_bytes()
    new = json.loads(current_bytes)["recipes"]
    assert old.keys() == new.keys(), "No recipe is added or deleted by this rule fix."
    assert gated(old) == gated(new), "The failed unreviewed model batch must remain gated."
    for key in gated(old):
        for field in CRITICAL_MODEL_FIELDS:
            estimate = old[key].get("estimated", {}).get(field, {})
            if estimate.get("method") == "llm" and not estimate.get("reviewed"):
                assert old[key][field] == new[key][field] and estimate == new[key]["estimated"][field]
    changes = {key: [field for field in RECIPE_TAG_FIELDS if old[key][field] != new[key][field]] for key in old}
    changes = {key: fields for key, fields in changes.items() if fields}
    dishes = {dish.key: dish for dish in curated_dishes() + release_dishes()}
    selected = choose(list(changes), args.count, args.seed)
    assert len(selected) == args.count and len(set(selected)) == args.count
    records = []
    for key in selected:
        dish = dishes[key]
        proposal = rule_tags(dish)
        records.append(
            {
                "key": key,
                "title": dish.title,
                "course": dish.course,
                "selection": "known regression" if key in KNOWN_CASES else "seeded random changed case",
                "changed_fields": changes[key],
                "before": {field: old[key][field] for field in RECIPE_TAG_FIELDS},
                "after": {field: new[key][field] for field in RECIPE_TAG_FIELDS},
                "after_methods": new[key]["estimated"],
                "fresh_rule_proposal": proposal.values,
                "model_batch_still_gated": key in gated(new),
                "incomplete_reason": proposal.incomplete_reason,
                "ingredients": [
                    {"name": line.name, "grams": line.grams, "original_text": line.text} for line in dish.lines
                ],
                "steps": dish.steps,
                "verdict": {field: None for field in changes[key]} | {"note": ""},
            }
        )
    packet = {
        "base_commit": base,
        "tag_file_sha256": hashlib.sha256(current_bytes).hexdigest(),
        "selection_seed": args.seed,
        "scope": "changed-case regression review, targeted plus seeded random; not independent population accuracy",
        "changed_recipe_count": len(changes),
        "changed_fields": dict(sorted(Counter(field for fields in changes.values() for field in fields).items())),
        "unreviewed_model_gate_before": len(gated(old)),
        "unreviewed_model_gate_after": len(gated(new)),
        "sample_count": len(records),
        "owner_confirmed": False,
        "records": records,
    }
    OUT.with_suffix(".json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 规则修复后的小范围复核（待人工确认）",
        "",
        "本表只核对变动后的标签，不复写上一轮审查，也不宣称总体准确率。"
        "优先包含已知回归案例，其余由固定种子从变动菜谱中抽取。",
        "",
        "同意某个新标签不表示原标签正确。未审核模型字段继续冻结；"
        "fresh_rule_proposal只是新规则建议，不是已放行的模型值。原料克重是release数据，不是另行实测。",
        "",
        f"变动菜谱：{len(changes)}；本次抽取：{len(records)}；未审核模型门禁：{len(gated(old))} → {len(gated(new))}。",
        "",
    ]
    for index, row in enumerate(records, 1):
        lines += [
            f"## {index}. {row['title']} ({row['key']})",
            "",
            f"抽样方式：{row['selection']}；原菜类：{row['course']}。",
            "",
            "| 变动字段 | 原值 | 新值 |",
            "|---|---|---|",
        ]
        for field in row["changed_fields"]:
            lines.append(f"| {field} | {json.dumps(row['before'][field])} | {json.dumps(row['after'][field])} |")
        if row["model_batch_still_gated"]:
            lines += ["", "**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**"]
        if row["incomplete_reason"]:
            lines += ["", f"资料不完整：{row['incomplete_reason']}。"]
        lines += ["", "原料证据：", ""]
        lines += [
            f"- {line['original_text'] or line['name']}（归一化 {line['grams']} g）" for line in row["ingredients"]
        ]
        lines += ["", "步骤证据：", "", row["steps"], "", "人工意见：待确认。", ""]
    OUT.with_suffix(".md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    compare_default(base)
    print(
        json.dumps(
            {
                key: packet[key]
                for key in (
                    "changed_recipe_count",
                    "changed_fields",
                    "unreviewed_model_gate_before",
                    "unreviewed_model_gate_after",
                    "sample_count",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
