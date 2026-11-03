"""Agreement of the reviewer's filled sample (review-table-20261024) with the batch's values, by stratum and field.

Only rows the reviewer marked 是 in "已亲自核对（填 是）" count; the others are reported as unchecked. A checked row
with no value, or with one this script cannot read ("是/否", a misspelt code: "无法识别，请重填"), is reported, and
counts neither as agreeing nor as disagreeing. The rows must be the sample's (`sample.json`). Offline, with a Python
that has openpyxl, from the repository root:
`python -I -X utf8 data-engineering/scripts/review_table_accuracy.py <filled sample.xlsx> --out <accuracy.md>`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_review_table import (  # noqa: E402
    CHECKED,
    FIELDS,
    OUT,
    RULE_STRATA,
    SAMPLE_SHEET,
    SKIP,
    YOUR_VALUE,
    code,
    same_value,
    shown,
    valid,
)
from review_sampling import interval, wilson  # noqa: E402

SAMPLE = OUT.parent / "sample.json"
GROUPS = ("table", "rule_decided", *RULE_STRATA, "all")
LABELS = {
    "table": "模型补全层（llm）",
    "rule_decided": "规则已定层",
    "rule_equals_model": "规则已定：规则值等于模型原值",
    "rule_differs_from_model": "规则已定：规则值不同于模型原值",
    "all": "合计",
}
COUNTS = ("rows", "checked", "agree", "unchecked", "checked_without_value", "unrecognized")


def tally() -> dict:
    counts = dict.fromkeys(COUNTS, 0)
    counts.update({"determinate_checked": 0, "determinate_agree": 0})
    return counts


def accuracy(rows: list[dict], sample: dict) -> dict:
    """Counts by group (the table layer, the rule-decided layer and its two strata, and all) and by field. `rows` are
    the filled sheet's `{"id", "field", "value", "checked"}`."""
    expected = {
        (recipe["id"], field): (recipe, value)
        for recipe in sample["recipes"]
        for field, value in recipe["values"].items()
    }
    seen = [(row["id"], row["field"]) for row in rows]
    if sorted(seen) != sorted(expected):
        raise SystemExit(f"the filled sheet's rows are not the sample's: {sorted(set(seen) ^ set(expected))[:5]}")
    groups = {name: tally() for name in GROUPS}
    fields = {name: tally() for name in FIELDS}
    differ, unrecognized = [], []
    for row in rows:
        recipe, batch_value = expected[(row["id"], row["field"])]
        counted = [groups[recipe["layer"]], groups["all"], fields[row["field"]]]
        if recipe["layer"] == "rule_decided":
            counted.append(groups[recipe["stratum"]])
        value = code(row["value"])
        if not row["checked"]:
            outcome = "unchecked"
        elif value is SKIP:
            outcome = "checked_without_value"
        elif value is not None and not valid(row["field"], value):
            outcome = "unrecognized"
            unrecognized.append(row)
        else:
            outcome = "checked"
        for counts in counted:
            counts["rows"] += 1
            counts[outcome] += 1
            if outcome == "checked" and same_value(batch_value, value):
                counts["agree"] += 1
            if outcome == "checked" and value is not None:
                counts["determinate_checked"] += 1
                if same_value(batch_value, value):
                    counts["determinate_agree"] += 1
        if outcome == "checked" and not same_value(batch_value, value):
            differ.append({**row, "batch_value": batch_value, "value": value})
    for counts in [*groups.values(), *fields.values()]:
        counts["accuracy"] = round(counts["agree"] / counts["checked"], 3) if counts["checked"] else None
        counts["wilson95"] = wilson(counts["agree"], counts["checked"])
        counts["determinate_accuracy"] = (
            round(counts["determinate_agree"] / counts["determinate_checked"], 3)
            if counts["determinate_checked"]
            else None
        )
        counts["determinate_wilson95"] = wilson(counts["determinate_agree"], counts["determinate_checked"])
    return {
        "groups": {name: counts for name, counts in groups.items() if counts["rows"]},
        "fields": {name: counts for name, counts in fields.items() if counts["rows"]},
        "differ": differ,
        "unrecognized": unrecognized,
    }


def read_filled(path: Path) -> list[dict]:
    from openpyxl import load_workbook

    sheet = load_workbook(path, read_only=True, data_only=True)[SAMPLE_SHEET]
    values = list(sheet.iter_rows(values_only=True))
    col = {name: index for index, name in enumerate(values[0])}
    return [
        {
            "id": cells[col["编号"]],
            "title": cells[col["菜名"]],
            "field": cells[col["字段"]],
            "value": cells[col[YOUR_VALUE]],
            "checked": str(cells[col[CHECKED]] or "").strip() == "是",
        }
        for cells in values[1:]
        if cells[col["编号"]]
    ]


def table(title: str, counted: dict, label) -> list[str]:
    lines = [
        "",
        f"| {title} | Rows | Checked | Agree | All-checked rate | Wilson 95% | Determinate n | Determinate agree | Determinate rate | Determinate Wilson 95% | Unchecked | Checked, no value | Unrecognized, refill |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for name, c in counted.items():
        share = "n/a" if c["accuracy"] is None else f"{c['accuracy']:.1%}"
        determinate_share = "n/a" if c["determinate_accuracy"] is None else f"{c['determinate_accuracy']:.1%}"
        lines.append(
            f"| {label(name)} | {c['rows']} | {c['checked']} | {c['agree']} | {share} | {interval(c['wilson95'])} "
            f"| {c['determinate_checked']} | {c['determinate_agree']} | "
            f"{determinate_share} "
            f"| {interval(c['determinate_wilson95'])} | {c['unchecked']} | {c['checked_without_value']} | {c['unrecognized']} |"
        )
    return lines


def markdown(result: dict, path: Path, sample: dict) -> str:
    lines = [
        f"# Sample accuracy of {sample['batch']}",
        "",
        f"Filled sample: SHA-256 `{hashlib.sha256(path.read_bytes()).hexdigest()}`; drawn: `sample.json` "
        f"({sample['size']} recipes, seed {sample['seed']}). This sample draws {sample['size']} recipes from the 116-recipe "
        "model-completed `llm-v3-20261103` batch, not all v3 tags. AI assisted with the initial comparison and draft "
        "discrepancy notes; a human reviewer checked each source recipe and tag, entered/confirmed the value, and marked "
        "the personal-check field. Only human-confirmed rows count; a reviewer null is unresolved and is excluded from "
        "the determinate denominator, while the all-checked result remains shown.",
    ]
    lines += table("Stratum", result["groups"], lambda name: f"{LABELS[name]} (`{name}`)")
    lines += table("Field", result["fields"], lambda name: f"`{name}`")
    lines += ["", f"无法识别，请重填: {len(result['unrecognized'])} rows.", ""]
    lines += [
        f"- {row['id']} {row['title']}: `{row['field']}` filled `{row['value']}`" for row in result["unrecognized"]
    ]
    lines += ["", f"Disagreements: {len(result['differ'])}.", ""]
    lines += [
        f"- {row['id']} {row['title']}: `{row['field']}` batch `{shown(row['batch_value'])}`, "
        f"reviewer `{shown(row['value'])}`"
        for row in result["differ"]
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Agreement of the reviewer's filled sample, by stratum and field.")
    parser.add_argument("filled", type=Path)
    parser.add_argument("--out", type=Path, help="also write the report here (markdown) and its JSON beside it")
    parser.add_argument("--sample", type=Path, default=SAMPLE, help="the sample.json the sheet was drawn from")
    args = parser.parse_args()
    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    result = accuracy(read_filled(args.filled), sample)
    report = markdown(result, args.filled, sample)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8", newline="\n")
        args.out.with_suffix(".json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
