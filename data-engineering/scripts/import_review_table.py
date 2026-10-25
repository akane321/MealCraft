"""Import the human reviewer's workbook for the frozen model batch as an AI-estimated batch (owner 2026-10-24).

The workbook's decisions were prefilled by AI and confirmed in chat by dish type, not checked row by row: its
"已亲自核对" column is empty on every row. So nothing here is a human label. ADR-0076's route:

- only a field the current rules leave open (`rule_suggestion` null in the reviewer packet) is imported, into
  `recipe-tags-v1/review-table-20261024` as model-decided and unreviewed: a role the reviewer may choose
  (`review_allowed_roles`), its staple (true exactly for one_bowl and staple), and protein sources of the vocabulary;
- a field the rules or the owner decide, a null, a skipped row, a role outside the reviewer's options, a staple that
  disagrees with its role, or an unknown code is not imported, and is listed with its reason;
- the batch's other part is the frozen fields the current rules decide, which `python -m app.data.recipe_tags`
  writes with the rule's value. The reviewer checks a fixed-seed sample of both parts in person (`sample.xlsx`):
  30 recipes with table values stratified by role, plus every recipe whose only table value is its protein
  sources, and 15 with rule-decided frozen fields, stratified by whether the rule's value is the model's and then
  by role. The sheet lists every recipe once, by id, and says neither which part a value is from nor the model's
  value. `review_table_accuracy.py` reports the sample's accuracy by stratum, which is published. Only then may the
  owner accept the batch (`python -m app.data.recipe_tags --accept-batch recipe-tags-v1/review-table-20261024`).

Offline, with a Python that has openpyxl, from the repository root:
`python -I -X utf8 data-engineering/scripts/import_review_table.py <workbook.xlsx> --base <commit>`.
It writes `decisions.json`, then, once the tag file carries it (`python -m app.data.recipe_tags` reads
`decisions.json`; run this script again after it), `sample.json` and `sample.xlsx`. It never writes the tag file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.data.recipe_tags import (  # noqa: E402
    CRITICAL_MODEL_FIELDS,
    MEAL_ROLES,
    OWNER_ROLES,
    PROTEIN_SOURCES,
    REVIEW_TABLE,
    REVIEW_TABLE_BATCH,
)
from app.data.release_v2 import release_dir  # noqa: E402
from app.data.tag_files import RECIPE_TAGS  # noqa: E402

PACKET = "data-engineering/docs/role-rules-20261023b/review.json"
OUT = ROOT / REVIEW_TABLE
SHEETS = ("1 可用池277道", "2 其余145道")
FIELDS = ("meal_role", "contains_staple", "protein_sources")
STAPLE_ROLES = frozenset({"one_bowl", "staple"})
SKIP = "<skip>"  # an empty cell or decision, or one left to the owner: the reviewer gave no value
PENDING = "待组长定"
SEED = 20261024
SAMPLE_SIZE = 30  # recipes with table values, by imported role; those with protein sources alone are all taken
RULE_SAMPLE_SIZE = 15  # recipes with rule-decided frozen fields, by stratum and role, at least one in each
PROTEIN_ONLY = "protein_sources only"
RULE_STRATA = ("rule_equals_model", "rule_differs_from_model")
STEPS_SHOWN = 400
SAMPLE_SHEET = "抽样核对"
CHECKED = "已亲自核对（填 是）"
YOUR_VALUE = "你看完后的值"
SEPARATORS = re.compile(r"[,，、]")
NOTE = re.compile(r"[（(][^（()）]*[）)]")  # a bracketed note, innermost first
REASONS = (
    "rule_decided_agrees",
    "rule_decided_conflicts",
    "owner_decided",
    "outside_allowed_roles",
    "left_open",
    "skipped_by_reviewer",
    "staple_inconsistent",
    "invalid_value",
)


def code(text):
    """A workbook cell as a value: 'staple（主食）' -> 'staple', 'pork（猪）,beef（牛）' -> ['beef', 'pork'],
    'true（是）' -> True, '[]' -> [], 'null（未知/不放行）' -> None, an empty cell or '待组长定' -> SKIP.
    A leading '被规则挡住 →' and bracketed notes are dropped (an unclosed bracket cuts its part); parts are separated
    by ',', '，' or '、'. Excel's TRUE and FALSE cells are booleans already. Anything else comes back as it is,
    for `valid` to judge."""
    if isinstance(text, bool):
        return text
    if text is None or not str(text).strip():
        return SKIP
    text = re.sub(r"^被规则挡住\s*→\s*", "", str(text).strip().lower())
    while NOTE.search(text):
        text = NOTE.sub("", text)
    parts = [re.split(r"[（(]", part)[0].strip() for part in SEPARATORS.split(text)]
    text = ",".join(parts)
    if text == PENDING:
        return SKIP
    if text in {"null", ""}:
        return None
    if text in {"true", "false"}:
        return text == "true"
    if text == "[]":
        return []
    if len(parts) > 1 or text in PROTEIN_SOURCES:
        return sorted(part for part in parts if part)
    return text


def valid(field: str, value) -> bool:
    """A value the field can hold, null aside: a meal role, a boolean staple, or protein sources of the vocabulary."""
    if field == "meal_role":
        return isinstance(value, str) and value in MEAL_ROLES
    if field == "contains_staple":
        return isinstance(value, bool)
    return isinstance(value, list) and set(value) <= set(PROTEIN_SOURCES)


def same_value(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return sorted(a) == sorted(b)
    return a == b and type(a) is type(b)


def intended(row: dict):
    """The value a workbook row's decision means: Claude's suggestion, the model's value, or the other value; a chat
    confirmation or a blocked row with no other value means the suggestion. No decision, or 跳过, is SKIP."""
    decision = str(row["decision"] or "").strip()
    if not decision or decision.startswith("跳过"):
        return SKIP
    if decision.startswith("同意Claude建议"):
        return code(row["claude"])
    if decision.startswith("同意模型原值"):
        return code(row["model"])
    if row["other"] not in (None, ""):
        return code(row["other"])
    if decision.startswith(("聊天确认", "被规则挡住")):
        return code(row["claude"])
    return SKIP


def judge(key: str, field: str, value, current: dict) -> str | None:
    """Why a workbook value is not imported, or None when it may be (a staple is then checked against its role)."""
    if value is SKIP:
        return "skipped_by_reviewer"
    if field != "protein_sources" and key in OWNER_ROLES:
        return "owner_decided"
    rule = current["rule_suggestion"][field]
    if rule is not None:
        return "rule_decided_agrees" if same_value(rule, value) else "rule_decided_conflicts"
    if value is None:
        return "left_open"
    if not valid(field, value):
        return "invalid_value"
    if field == "meal_role" and value not in current["review_allowed_roles"]:
        return "outside_allowed_roles"
    return None


def decide(rows: list[dict], packet: dict[str, dict]) -> tuple[dict, list[dict]]:
    """The imported values by recipe, and every workbook value not imported with its reason."""
    by_recipe: dict[str, dict] = defaultdict(dict)
    for row in rows:
        by_recipe[row["id"]][row["field"]] = row
    missing = sorted(set(by_recipe) - set(packet))
    if missing:
        raise SystemExit(f"recipes not in the reviewer packet: {missing[:5]}")
    accepted, skipped = {}, []
    for key in sorted(by_recipe):
        current = packet[key]
        values = {field: intended(row) for field, row in by_recipe[key].items()}
        reasons = {field: judge(key, field, value, current) for field, value in values.items()}
        if "meal_role" in values and reasons["meal_role"] is None:
            derived = values["meal_role"] in STAPLE_ROLES
            staple = values.get("contains_staple", SKIP)
            if staple is not SKIP and staple is not derived:
                reasons["meal_role"] = reasons["contains_staple"] = "staple_inconsistent"
            else:
                values["contains_staple"], reasons["contains_staple"] = derived, None
        elif reasons.get("contains_staple", "") is None:
            reasons["contains_staple"] = reasons.get("meal_role") or "left_open"  # a staple follows its role
        kept = {field: values[field] for field in FIELDS if field in reasons and reasons[field] is None}
        if "protein_sources" in kept:
            kept["protein_sources"] = [source for source in PROTEIN_SOURCES if source in kept["protein_sources"]]
        if kept:
            accepted[key] = {"title": current["title"], **kept}
        skipped += [
            {
                "id": key,
                "title": current["title"],
                "field": field,
                "value": None if values[field] is SKIP else values[field],
                "rule": current["rule_suggestion"][field],
                "reason": reason,
            }
            for field, reason in reasons.items()
            if reason
        ]
    return accepted, skipped


def counts(accepted: dict, skipped: list[dict]) -> dict:
    by_field = {field: Counter() for field in FIELDS}
    for values in accepted.values():
        for field in FIELDS:
            by_field[field]["imported"] += field in values
    for item in skipped:
        by_field[item["field"]][item["reason"]] += 1
    reasons = Counter(item["reason"] for item in skipped)
    return {
        "recipes_with_an_imported_value": len(accepted),
        "imported": {field: by_field[field]["imported"] for field in FIELDS},
        "skipped": {reason: reasons[reason] for reason in REASONS},
        "by_field": {field: {name: n for name, n in by_field[field].items() if n} for field in FIELDS},
        "imported_meal_roles": dict(
            sorted(Counter(v["meal_role"] for v in accepted.values() if "meal_role" in v).items())
        ),
    }


def draw(strata: dict[str, list[str]], size: int, minimum: int) -> list[tuple[str, str]]:
    """`size` keys over the strata: each at least `minimum` (or all it has), the rest by size (largest remainder),
    drawn with `SEED`."""
    total = sum(map(len, strata.values()))
    if not total:
        return []
    quota = {name: min(len(keys), max(minimum, len(keys) * size // total)) for name, keys in strata.items()}
    remainder = {name: len(keys) * size / total - quota[name] for name, keys in strata.items()}
    while sum(quota.values()) < min(size, total):
        name = max(sorted(strata), key=lambda s: remainder[s])
        quota[name], remainder[name] = quota[name] + 1, remainder[name] - 1
    while sum(quota.values()) > size:  # the minimums overshot: take back from the most over-served stratum
        over = [s for s in sorted(strata) if quota[s] > minimum]
        if not over:
            break  # more strata than `size`: each keeps its minimum
        name = min(over, key=lambda s: remainder[s])
        quota[name], remainder[name] = quota[name] - 1, remainder[name] + 1
    rng = random.Random(SEED)
    return [(name, key) for name in sorted(strata) for key in sorted(rng.sample(sorted(strata[name]), quota[name]))]


def draw_sample(accepted: dict) -> list[tuple[str, str]]:
    """`SAMPLE_SIZE` recipes with an imported value, stratified by the imported meal role, every stratum at least one;
    then every recipe whose only table value is its protein sources (owner 2026-10-24: none is accepted unseen)."""
    strata: dict[str, list[str]] = defaultdict(list)
    for key in sorted(accepted):
        strata[accepted[key].get("meal_role", PROTEIN_ONLY)].append(key)
    picked = draw(strata, SAMPLE_SIZE, 1)
    return picked + [(PROTEIN_ONLY, key) for key in strata[PROTEIN_ONLY] if (PROTEIN_ONLY, key) not in picked]


def rule_part(entries: dict[str, dict], packet: dict[str, dict]) -> dict[str, dict]:
    """The frozen fields the rules decide (`rule` in the review batch) by recipe, the owner's dishes left out: whether
    every one of them is the frozen model value (`stored` in the reviewer packet), and the role among them."""
    part = {}
    for key, entry in entries.items():
        fields = [
            name
            for name in CRITICAL_MODEL_FIELDS
            if entry["estimated"].get(name, {}).get("batch") == REVIEW_TABLE_BATCH
            and entry["estimated"][name]["method"] == "rule"
        ]
        if fields and key not in OWNER_ROLES:
            same = all(same_value(entry[name], packet[key]["stored"][name]) for name in fields)
            part[key] = {
                "stratum": RULE_STRATA[0 if same else 1],
                "role": entry["meal_role"] if "meal_role" in fields else PROTEIN_ONLY,
                "values": {name: entry[name] for name in fields},
            }
    return part


def draw_rule_sample(rules: dict[str, dict]) -> list[tuple[str, str, str]]:
    """`RULE_SAMPLE_SIZE` recipes of the rule-decided part, by whether the rule's values are the model's and then by
    role, at least one in each, the rest by size: `(stratum, role, key)`."""
    cells: dict[str, list[str]] = defaultdict(list)
    for key in sorted(rules):
        cells[f"{rules[key]['stratum']}/{rules[key]['role']}"].append(key)
    return [(*cell.split("/"), key) for cell, key in draw(cells, RULE_SAMPLE_SIZE, 1)]


def carried(entries: dict[str, dict], accepted: dict) -> bool:
    """Whether the tag file carries every imported value in the review batch (it was regenerated after the import)."""
    return all(
        entries[key][name] == value and entries[key]["estimated"][name]["batch"] == REVIEW_TABLE_BATCH
        for key, values in accepted.items()
        for name, value in values.items()
        if name in FIELDS
    )


def shown(value) -> str:
    """A value as the code the reviewer reads and types."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(value) if value else "[]"
    return "null" if value is None else str(value)


def read_rows(path: Path) -> tuple[list[dict], int]:
    """The workbook's field rows, and how many are marked personally checked."""
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    rows = []
    for sheet in SHEETS:
        values = list(workbook[sheet].iter_rows(values_only=True))
        col = {name: index for index, name in enumerate(values[0])}
        other = col[next(name for name in col if str(name).startswith("其他值"))]
        checked = col[next(name for name in col if str(name).startswith("已亲自核对"))]
        for cells in values[1:]:
            if cells[col["编号"]]:
                rows.append(
                    {
                        "id": cells[col["编号"]],
                        "field": re.split(r"[（(]", str(cells[col["字段"]]))[0],
                        "model": cells[col["AI模型原值"]],
                        "claude": cells[col["Claude建议"]],
                        "decision": cells[col["你的决定"]],
                        "other": cells[other],
                        "checked": str(cells[checked] or "").strip() == "是",
                    }
                )
    return rows, sum(row["checked"] for row in rows)


def steps_of(keys: set[str]) -> dict[str, str]:
    steps = {}
    with (release_dir() / "recipes.jsonl").open(encoding="utf-8") as handle:
        for record in map(json.loads, filter(str.strip, handle)):
            if record["recipe_id"] in keys:
                text = " / ".join(s["text"].strip() for s in record["instructions"] if s["text"].strip())
                steps[record["recipe_id"]] = text[:STEPS_SHOWN]
    return steps


INSTRUCTIONS = [
    "AI 标签抽样核对（recipe-tags-v1/review-table-20261024）",
    "",
    f"这些菜按固定种子 {SEED} 抽自这一批。一部分的值来自你的复核表（AI 预填、在聊天里按菜品类型确认，",
    "没有人逐条看过食材），另一部分的值是现行规则给的。两部分现在都记为未复核；表里不标来源，请一律独立判断。",
    "这次核对的结果决定这一批能不能被组长接受。",
    "",
    "每一行是一道菜的一个字段。请你本人逐行：",
    "1. 先看“食材（克）”和“步骤（前 400 字）”，再看“本批的值”。不要只凭菜名判断。",
    "2. 在“你看完后的值”里填你认为正确的值（同意也照抄一遍，不能空着），用代码：",
    "   餐型角色：" + " / ".join(MEAL_ROLES) + " 之一；",
    "   是否自带主食：true 或 false（one_bowl 和 staple 是 true，其他角色是 false），不要填“是/否”；",
    "   主要蛋白来源：用逗号分隔 " + ", ".join(PROTEIN_SOURCES) + "；没有主要蛋白填 []；",
    "   看不出来：填 null。认不出的写法会被标为“无法识别，请重填”。",
    "3. 只有你亲自看完这一行的食材和步骤之后，才在“已亲自核对（填 是）”里填“是”。没看的行不要填。",
    "   没填“是”的行不计入准确率，只计为“未核对”。",
    "4. 不要改其他栏，不要增删行；有话可写在“备注”里。",
    "",
    "准确率由 data-engineering/scripts/review_table_accuracy.py 分层计算并公开。组长看过准确率后，",
    "才决定是否接受这一批（python -m app.data.recipe_tags --accept-batch recipe-tags-v1/review-table-20261024）。",
]
SAMPLE_COLUMNS = (
    "序号",
    "编号",
    "菜名",
    "类别",
    "食材（克）",
    "步骤（前 400 字）",
    "字段",
    "本批的值",
    YOUR_VALUE,
    CHECKED,
    "备注",
)


def write_sample_xlsx(path: Path, recipes: list[dict]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = Workbook()
    guide = workbook.active
    guide.title = "说明"
    for line in INSTRUCTIONS:
        guide.append([line])
    guide["A1"].font = Font(bold=True)
    guide.column_dimensions["A"].width = 110
    sheet = workbook.create_sheet(SAMPLE_SHEET)
    sheet.append(SAMPLE_COLUMNS)
    # Every recipe once, by id, its fields of both parts together: nothing on the sheet tells which part a value is.
    merged: dict[str, dict] = {}
    for recipe in recipes:
        merged.setdefault(recipe["id"], recipe | {"values": {}})["values"].update(recipe["values"])
    for number, key in enumerate(sorted(merged), 1):
        recipe = merged[key]
        ingredients = "; ".join(
            f"{line['name']} {line['grams'] if line['grams'] is not None else '?'} g（{line['text']}）"
            for line in recipe["ingredients"]
        )
        for field in FIELDS:
            if field in recipe["values"]:
                sheet.append(
                    [number, key, recipe["title"], recipe["course"], ingredients, recipe["steps"], field]
                    + [shown(recipe["values"][field]), None, None, None]
                )
    widths = (6, 20, 30, 11, 60, 60, 16, 16, 16, 14, 24)
    fill = PatternFill("solid", fgColor="FFF2CC")
    for index, width in enumerate(widths):
        letter = chr(ord("A") + index)
        sheet.column_dimensions[letter].width = width
        sheet[f"{letter}1"].font = Font(bold=True)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for cell in row[8:11]:
            cell.fill = fill
    sheet.freeze_panes = "C2"
    workbook.save(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sample(packet: dict[str, dict], accepted: dict, rules: dict[str, dict]) -> dict:
    """`sample.json` and `sample.xlsx` over both parts of the batch."""
    picked = [("table", stratum, None, key, accepted[key]) for stratum, key in draw_sample(accepted)]
    picked += [("rule_decided", s, role, key, rules[key]["values"]) for s, role, key in draw_rule_sample(rules)]
    steps = steps_of({key for *_, key, _ in picked})
    recipes = [
        {
            "id": key,
            "title": packet[key]["title"],
            "course": packet[key]["course"],
            "layer": layer,
            "stratum": stratum,
            **({"role": role} if role else {}),
            "values": {field: values[field] for field in FIELDS if field in values},
            "ingredients": packet[key]["ingredients"],
            "steps": steps.get(key, ""),
        }
        for layer, stratum, role, key, values in picked
    ]
    table = Counter(values.get("meal_role", PROTEIN_ONLY) for values in accepted.values())
    cells = Counter((item["stratum"], item["role"]) for item in rules.values())
    drawn = Counter((r["layer"], r["stratum"], r.get("role")) for r in recipes)
    sample = {
        "batch": REVIEW_TABLE_BATCH,
        "seed": SEED,
        "size": len(recipes),
        "distinct_recipes": len({recipe["id"] for recipe in recipes}),
        "layers": {
            "table": {name: {"recipes": n, "drawn": drawn["table", name, None]} for name, n in sorted(table.items())},
            "rule_decided": {
                stratum: {
                    role: {"recipes": n, "drawn": drawn["rule_decided", stratum, role]}
                    for (s, role), n in sorted(cells.items())
                    if s == stratum
                }
                for stratum in RULE_STRATA
            },
        },
        "how_to_check": "data-engineering/docs/review-table-20261024/README.md; fill sample.xlsx in person",
        "recipes": [
            {
                name: recipe[name]
                for name in ("id", "title", "course", "layer", "stratum", "role", "values")
                if name in recipe
            }
            for recipe in recipes
        ],
    }
    (OUT.parent / "sample.json").write_text(
        json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    write_sample_xlsx(OUT.parent / "sample.xlsx", recipes)
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the reviewer's workbook as an unreviewed AI-estimated batch.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--base", help="the commit the import is made against (default: HEAD)")
    args = parser.parse_args()
    base = subprocess.check_output(["git", "rev-parse", args.base or "HEAD"], cwd=ROOT, text=True).strip()
    packet_path = ROOT / PACKET
    packet = {row["id"]: row for row in json.loads(packet_path.read_text(encoding="utf-8"))["frozen_rows"]}
    rows, checked = read_rows(args.workbook)
    accepted, skipped = decide(rows, packet)
    summary = counts(accepted, skipped)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    decisions = {
        "batch": REVIEW_TABLE_BATCH,
        "method": "llm",
        "reviewed": False,
        "note": (
            "AI-prefilled values the reviewer confirmed in chat by dish type, not checked row by row. Imported as an "
            "unreviewed model-decided batch, only where the current rules leave the field open; never a human label."
        ),
        "provenance": {
            "workbook": "the reviewer's review workbook (not committed)",
            "workbook_sha256": sha256(args.workbook),
            "sheets": list(SHEETS),
            "rows": len(rows),
            "recipes": len({row["id"] for row in rows}),
            "personally_checked_rows": checked,
            "personally_checked_note": "the 已亲自核对 column is empty on every row" if not checked else "not empty",
            "packet": PACKET,
            "packet_sha256": sha256(packet_path),
            "base_commit": base,
            "owner_decisions": "backend/app/data/recipe_tags.py OWNER_ROLES (owner 2026-10-24) win over the workbook",
            "generated_by": "data-engineering/scripts/import_review_table.py",
        },
        "counts": summary,
        "accepted": accepted,
        "skipped": skipped,
    }
    OUT.write_text(json.dumps(decisions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    entries = json.loads((ROOT / RECIPE_TAGS).read_text(encoding="utf-8"))["recipes"]
    if not carried(entries, accepted):
        raise SystemExit(
            "The tag file does not carry decisions.json yet: run `python -m app.data.recipe_tags` "
            "from backend, then this script again for the sample."
        )
    rules = rule_part(entries, packet)
    if not rules:
        raise SystemExit(
            "The tag file carries no rule-decided part of the batch: run `python -m app.data.recipe_tags` "
            "from backend, then this script again for the sample."
        )
    sample = write_sample(packet, accepted, rules)
    print(f"sample: {sample['size']} recipes; {json.dumps(sample['layers'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
