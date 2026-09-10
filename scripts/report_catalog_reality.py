"""Measure what the committed catalog can actually express, for episode authors.

Held-out episodes are written against a fixed catalog, and a constraint the
catalog cannot express produces an episode that tests nothing. "No dairy" reads
like a real safety constraint; against a catalog where one recipe contains
dairy, a system that ignores the constraint entirely still answers correctly.

The numbers below decide which constraints are worth writing, so they are
measured rather than remembered. Regenerate after any catalog change:

    python scripts/report_catalog_reality.py

`--check` fails when the committed document is stale, which is what CI runs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evaluation" / "heldout-catalog-reality.md"

RECIPES = ROOT / "data" / "recipes" / "recipes.json"
INGREDIENTS = ROOT / "data" / "ingredients" / "ingredients.json"
PRODUCTS_V2 = ROOT / "data" / "fixtures" / "fairprice-products-v2.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def measure() -> dict:
    recipes = load(RECIPES)
    ingredients = {row["normalized_name"]: row for row in load(INGREDIENTS)}
    products = load(PRODUCTS_V2)

    allergens = sorted({row["allergen"] for row in ingredients.values() if row.get("allergen")})
    allergen_rows = []
    for allergen in allergens:
        hit = {
            r["slug"]
            for r in recipes
            if any(ingredients.get(i["ingredient"], {}).get("allergen") == allergen for i in r["ingredients"])
        }
        allergen_rows.append((allergen, len(hit), len(recipes) - len(hit)))

    tags = Counter(tag for r in recipes for tag in r["dietary_tags"])
    times = sorted(r["prep_time_minutes"] + r["cook_time_minutes"] for r in recipes)
    prices = sorted(p["price_sgd"] for p in products)

    sizes: dict[str, int] = {}
    for product in products:
        for key in product["ingredient_keys"]:
            sizes[key] = sizes.get(key, 0) + 1

    nutrition = {
        metric: sorted(r["nutrition"][metric] for r in recipes)
        for metric in ("calories_kcal", "protein_g", "sodium_mg")
    }
    return {
        "recipes": recipes,
        "ingredients": ingredients,
        "products": products,
        "allergen_rows": allergen_rows,
        "tags": tags,
        "times": times,
        "prices": prices,
        "multi_size": sorted(key for key, count in sizes.items() if count > 1),
        "nutrition": nutrition,
    }


def band(values: list[float]) -> str:
    return f"{values[0]} – {values[-1]}（中位 {values[len(values) // 2]}）"


def render(m: dict) -> str:
    recipes = m["recipes"]
    total = len(recipes)
    lines: list[str] = []
    add = lines.append

    add("# 目录现状与选题建议")
    add("")
    add("> 由 `scripts/report_catalog_reality.py` 生成，请勿手工编辑。目录变化后重新生成。")
    add("")
    add("写 held-out 题之前先看这一页。**目录表达不了的约束，写出来的题什么都测不到**——")
    add("「不吃奶制品」读起来像个真实的安全约束，但如果目录里只有一道菜含奶制品，")
    add("一个完全忽略该约束的系统照样能答对。")
    add("")
    add(f"当前目录：**{total} 道菜谱 / {len(m['ingredients'])} 种食材 / {len(m['products'])} 个商品（v2 快照）**")
    add("")

    add("## 过敏原：哪些值得写")
    add("")
    add("| 过敏原 | 命中菜数 | 剩余可选 | 作为安全约束的强度 |")
    add("|---|---:|---:|---|")
    for allergen, hit, left in sorted(m["allergen_rows"], key=lambda row: -row[1]):
        share = hit / total
        if share >= 0.2:
            strength = "**强**，值得单独成题"

        elif share >= 0.1:
            strength = "中等，建议与其他约束组合"
        else:
            strength = "**太弱**，单独使用测不出东西"
        add(f"| `{allergen}` | {hit} | {left} | {strength} |")
    add("")
    add("排除的菜越少，忽略该约束被发现的概率越低。弱过敏原不是不能用，")
    add("但必须和预算、时间或另一个过敏原组合，让系统必须真的过滤。")
    add("")

    add("## 饮食标签")
    add("")
    add("| 标签 | 菜数 |")
    add("|---|---:|")
    for tag, count in m["tags"].most_common():
        add(f"| `{tag}` | {count} |")
    add("")

    add("## 烹饪总时长（准备 + 烹饪）")
    add("")
    times = m["times"]
    add(f"- 区间：{band(times)} 分钟")
    for limit in (20, 30, 40):
        fits = sum(1 for t in times if t <= limit)
        note = "**填不满七餐，写出来会变成无意打中的不可行题**" if fits < 7 else "可用"
        add(f"- ≤ {limit} 分钟：{fits} 道 —— {note}")
    add("")

    add("## 营养区间（每份）")
    add("")
    add("| 指标 | 区间 |")
    add("|---|---|")
    for metric, values in m["nutrition"].items():
        add(f"| `{metric}` | {band(values)} |")
    add("")
    add("写数值约束前先用这个区间估一下会剩几道菜。要求「每份至少 40g 蛋白质」时，")
    add("先确认有几道菜达得到。")
    add("")

    add("## 价格与包装")
    add("")
    prices = m["prices"]
    add(f"- 商品单价：S${prices[0]} – S${prices[-1]}（中位 S${prices[len(prices) // 2]}）")
    add(f"- **有多种包装规格的食材：{len(m['multi_size'])} 种** —— {', '.join(f'`{k}`' for k in m['multi_size'])}")
    add("")
    add("`budget_package` 类的题应当围绕这些食材构造，因为只有它们能触发混合包装。")
    add("对只有单一规格的食材，能测的只是包装向上取整和总价是否等于各行之和。")
    add("")

    add("## 已知的表达力限制")
    add("")
    add("这些不是缺陷，是当前目录规模的结果。写题时绕开，并在评价报告里如实说明：")
    add("")
    add(f"- 目录只有 {total} 道菜。填满七个餐位后，任何较紧的约束都会逼出重复。")
    add("- 没有 `equipment`、`difficulty`、`method` 字段，按厨具或难度筛选目前做不到。")
    add("- 过敏原只有上表这几种，覆盖不到现实范围。")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    rendered = render(measure())
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != rendered:
            print(f"{OUT.relative_to(ROOT).as_posix()} is stale. Run scripts/report_catalog_reality.py")
            return 1
        print(f"{OUT.relative_to(ROOT).as_posix()} is current.")
        return 0
    OUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
