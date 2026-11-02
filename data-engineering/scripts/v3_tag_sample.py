"""Draw the in-person acceptance sample for the model batch of data release v3 (ADR-0111, like ADR-0094).

The batch `recipe-tags-v1/llm-v3-20261103` holds the values the model decided for the recipes v3 added, where the
rules left a field open. The planner does not read them until the owner accepts the batch
(`python -m app.data.recipe_tags --accept-batch recipe-tags-v1/llm-v3-20261103`). This script draws a fixed-seed sample
of that batch, stratified by the batch's meal role, and writes `sample.json` and `sample.xlsx` into
`data-engineering/docs/tag-sample-20261103/`. The reviewer columns are empty. The sheet shows no source and no model
value. It has the same layout as the review-table sheet, so `review_table_accuracy.py --sample` scores it:

    python -I -X utf8 data-engineering/scripts/v3_tag_sample.py
    python -I -X utf8 data-engineering/scripts/review_table_accuracy.py <filled.xlsx> \\
        --sample data-engineering/docs/tag-sample-20261103/sample.json \\
        --out data-engineering/docs/tag-sample-20261103/accuracy.md

Offline, from the repository root, with a Python that has openpyxl (`uv run --project backend --with openpyxl`).
It never writes the tag file.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import import_review_table as irt  # noqa: E402
from app.data.recipe_tags import CRITICAL_MODEL_FIELDS, V3_LLM_BATCH, release_dishes  # noqa: E402
from app.data.tag_files import RECIPE_TAGS  # noqa: E402

SEED = 20261103
SIZE = 40  # recipes; about a third of the batch, at least one per stratum
OUT = irt.ROOT / "data-engineering/docs/tag-sample-20261103"
INSTRUCTIONS = [
    f"AI 标签抽样核对（{V3_LLM_BATCH}）",
    "",
    f"这些菜是数据版本 v3 新增的菜，标签由 AI 模型在规则留空的字段上估计，按固定种子 {SEED} 抽样。",
    "表里不标来源，请独立判断。这次核对的结果决定这一批能不能被组长接受。",
    "",
    "每一行是一道菜的一个字段。请你本人逐行：",
    "1. 先看“食材（克）”和“步骤（前 400 字）”，再看“本批的值”。不要只凭菜名判断。",
    "2. 在“你看完后的值”里填你认为正确的值（同意也照抄一遍，不能空着），用代码：",
    "   餐型角色：" + " / ".join(irt.MEAL_ROLES) + " 之一；",
    "   是否自带主食：true 或 false（one_bowl 和 staple 是 true，其他角色是 false），不要填“是/否”；",
    "   主要蛋白来源：用逗号分隔 " + ", ".join(irt.PROTEIN_SOURCES) + "；没有主要蛋白填 []；",
    "   看不出来：填 null。认不出的写法会被标为“无法识别，请重填”。",
    "3. 只有你亲自看完这一行的食材和步骤之后，才在“已亲自核对（填 是）”里填“是”。没看的行不要填。",
    "   没填“是”的行不计入准确率，只计为“未核对”。",
    "4. 不要改其他栏，不要增删行；有话可写在“备注”里。",
]


def batch_values() -> dict[str, dict]:
    """The model's values of the v3 batch by recipe: only the fields the batch decided."""
    entries = json.loads((irt.ROOT / RECIPE_TAGS).read_text(encoding="utf-8"))["recipes"]
    found = {}
    for key, entry in entries.items():
        values = {
            name: entry[name]
            for name in CRITICAL_MODEL_FIELDS
            if entry["estimated"].get(name, {}).get("batch") == V3_LLM_BATCH
        }
        if values:
            found[key] = values
    return found


def main() -> None:
    values = batch_values()
    strata: dict[str, list[str]] = defaultdict(list)
    for key in sorted(values):
        strata[values[key].get("meal_role", irt.PROTEIN_ONLY)].append(key)
    irt.SEED = SEED  # `irt.draw` reads it at call time
    picked = irt.draw(strata, SIZE, 1)
    dishes = {dish.key: dish for dish in release_dishes()}
    steps = irt.steps_of({key for _, key in picked})
    recipes = [
        {
            "id": key,
            "title": dishes[key].title,
            "course": dishes[key].course,
            "layer": "table",
            "stratum": stratum,
            "values": values[key],
            "ingredients": [
                {"name": line.name, "grams": line.grams, "text": line.text or line.name} for line in dishes[key].lines
            ],
            "steps": steps.get(key, ""),
        }
        for stratum, key in picked
    ]
    sizes = Counter({name: len(keys) for name, keys in strata.items()})
    drawn = Counter(recipe["stratum"] for recipe in recipes)
    sample = {
        "batch": V3_LLM_BATCH,
        "seed": SEED,
        "size": len(recipes),
        "distinct_recipes": len({recipe["id"] for recipe in recipes}),
        "batch_recipes": len(values),
        "batch_values": sum(map(len, values.values())),
        "layers": {"table": {name: {"recipes": sizes[name], "drawn": drawn[name]} for name in sorted(sizes)}},
        "how_to_check": "data-engineering/docs/tag-sample-20261103/README.md; fill sample.xlsx in person",
        "recipes": [
            {name: recipe[name] for name in ("id", "title", "course", "layer", "stratum", "values")}
            for recipe in recipes
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample.json").write_text(
        json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    irt.write_sample_xlsx(OUT / "sample.xlsx", recipes, INSTRUCTIONS)
    print(f"sample: {sample['size']} of {sample['batch_recipes']} recipes, {sample['batch_values']} batch values")
    print(json.dumps(sample["layers"], ensure_ascii=False))


if __name__ == "__main__":
    main()
