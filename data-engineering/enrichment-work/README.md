# Release v2 enrichment work packets

决定依据：私有知识库 `ADR-0030`。本文件是三份工作（A、B、C）共用的**唯一**说明书。

## 给组员：三步开始

1. 拉取最新 `main`，新建分支 `data/v2-part-<你的字母>`。
2. 在 `data-engineering/` 目录下打开 Claude Code 或 Codex，对它说：
   > 读 `enrichment-work/README.md`，按说明完成 part <字母> 的全部工作，署名 `claude/<你的名字>`（或 `codex/<你的名字>`）。
3. 随时可以停下。额度用完或者关机都没关系，下次说同一句话，会从停下的地方继续。
   做完一批就提交并推送 `enrichment-work/part-<字母>/` 下的两个 `*.output.jsonl`。三份结果互不重叠，最后直接合并。

**只改自己那份的输出文件。** 不要改输入文件、别人的文件、脚本或本说明。

---

## Instructions for the AI agent (Claude or Codex)

### Why this exists

MealCraft plans a household's week of meals under hard constraints (allergens,
diet, budget, cooking time) and reports nutrition. Release v2 is its recipe
database: about 10,000 recipes across cuisines, weighted towards Asian food for
users in Singapore. Every recipe needs its time, servings, course, cuisine,
meal types and difficulty, and every ingredient its nutrition and unit weights,
so the planner can compute per-serving nutrition and respect time limits.

What matters most, in order: numbers that are **plausible and traceable**
(a stated source, or an estimate that says it is one), then **consistency**
(the same kind of thing judged the same way), then speed. A figure off by 15%
is acceptable; an invented source, an unexplained outlier or a silently wrong
unit is not. You need **web search** enabled for the ingredient items (Claude
Code has it; in Codex enable it).

Several agents may work on one part at once: give each a different
`--shard i/n` on `next` (for example `--shard 1/3`, `2/3`, `3/3`); `submit`
is safe to call concurrently.

You are enriching one part of the MealCraft recipe release. Work only through
`scripts/v2_packet.py`, from the `data-engineering/` directory. Never edit an
`*.input.jsonl` file, another part's files, or any script.

### Loop

```text
python scripts/v2_packet.py status --part X
python scripts/v2_packet.py next --part X --kind ingredients --n 5     # do ingredients first (add --shard i/n if several agents share part X)
# ... produce one JSON object per item, one per line, into a scratch file ...
python scripts/v2_packet.py submit --part X --kind ingredients --by "claude/<name>" < scratch.jsonl
```

Repeat until `next` prints nothing for `ingredients`, then do the same for
`recipes` with `--n 25`.

**Work in large batches and keep it short; this is what makes the job
finishable.** Read this file once per session, not once per batch. Take 5
ingredients or 25 recipes at a time, write all their results into one scratch
file in one go, and submit once. Keep every `evidence`, `basis` and `notes`
string under about 15 words. Do not re-read items you have already submitted. `submit` validates every line and appends only
valid ones; fix and resubmit any line it rejects. Items already accepted are
skipped, so resubmitting is always safe. Commit the two output files every few
batches so a stopped session loses nothing.

Items marked `"overlap_copy": true` are also done by another part on purpose, to
measure agreement. Do them independently, exactly like any other item.

### Ingredient items

Input fields: `ingredient_id`, `canonical_name`, `food_group`, `aliases`,
`units_to_weigh`, `examples` (how recipes write it). An id ending in `#cooked` is
the cooked form of that ingredient.

Use **web search** for every ingredient. Prefer, in order: USDA FoodData Central
pages, other national food-composition tables, manufacturer nutrition labels,
reputable weight charts (King Arthur, etc.). When no source gives a figure, give
a reasoned estimate and say so in `notes`. Never leave a number out.

Output one object:

```json
{"ingredient_id": "ING_BUTTER",
 "nutrition_form": "unsalted butter, as measured in recipes",
 "nutrition_per_100g": {"energy_kcal": 717, "protein_g": 0.85, "carbohydrate_g": 0.06,
                        "fat_g": 81.1, "sodium_mg": 11, "sugar_g": 0.06},
 "unit_grams": [{"unit": "cup", "grams": 227, "basis": "USDA: 1 cup = 227 g"},
                {"unit": "stick", "grams": 113, "basis": "US stick = 1/2 cup"}],
 "allergen_opinion": ["milk"],
 "sources": [{"title": "USDA FDC 173430 Butter, without salt", "url": "https://fdc.nal.usda.gov/..."}],
 "confidence": 0.95,
 "notes": ""}
```

- `nutrition_per_100g` is for the form the `examples` measure: dry rice and
  pasta, raw meat, canned goods as canned. A `#cooked` id is the cooked form.
- `unit_grams` gives grams for **one** of every unit in `units_to_weigh`, which
  always includes `cup`; say in `basis` which form and packing you assumed
  (agar strands and agar powder differ about twentyfold). `cup`
  is one US cup (236.6 ml) of the ingredient as measured (packed brown sugar,
  chopped onion); count units (`piece`, `clove`, `slice`, `stick`, `head`,
  `bunch`, `can` ...) are one typical item, medium when no size is given.
- Energy must agree with the macros (4/4/9 kcal per g) within about a third. If
  it genuinely does not (alcohol, fibre, sugar alcohols), write
  `energy_check_exception` and the reason in `notes`.
- `allergen_opinion` is only compared with MealCraft's rule table, never applied.
  Use `milk, eggs, fish, crustaceans, tree_nuts, peanuts, gluten, soy, sesame`.

### Recipe items

Input fields: `candidate_id`, `title`, `servings` (null when the source does not
say), `ingredients` (each with `index`, `text`, and `needs_amount`), `steps`,
`stated_durations` (durations found in the steps by rule), `cuisine_hint`.

Use only the recipe itself; no web search is needed. Output one object:

```json
{"candidate_id": "recipenlg:12345",
 "prep_minutes": 15, "cook_minutes": 40, "passive_minutes": 0, "time_basis": "stated",
 "servings": 4,
 "course": "main", "cuisine": "chinese", "meal_types": ["lunch", "dinner"], "difficulty": "easy",
 "line_estimates": [{"index": 7, "quantity": 0.5, "unit": "tsp", "basis": "'salt to taste' for 4 servings"}],
 "evidence": {"time": "step 3 'simmer 30 minutes', step 4 'bake 10 minutes'; prep estimated",
              "servings": "stated in source", "course": "stir-fried meat with rice",
              "cuisine": "soy sauce, oyster sauce, 'Kung Pao' in title", "meal_types": "main dish",
              "difficulty": "one pan, four steps"},
 "confidence": {"time": 0.8, "servings": 1.0, "course": 0.9, "cuisine": 0.95, "meal_types": 0.8,
                "difficulty": 0.8}}
```

- Times are whole minutes for the whole recipe: `prep_minutes` hands-on work,
  `cook_minutes` on heat or in an appliance, `passive_minutes` unattended waiting
  (chilling, marinating, rising, cooling). Use the stated durations; estimate the
  rest as an experienced home cook. Follow the recipe text literally ("soak
  overnight" is 480 passive minutes). `time_basis` is `stated` only when every
  cooking and waiting step gives a duration.
- `servings`: keep the source's number when it is given. When it is null,
  estimate from the quantities and say how in `evidence.servings`.
- `course`, `cuisine`, `meal_types`, `difficulty` use the vocabularies in
  `config/recipe_vocabulary.json`. `cuisine_hint` came from a keyword rule and
  may be wrong; decide from the recipe. `course` says what the dish is
  (`dessert`, `drink` ...); `meal_types` says when it is eaten, and desserts,
  drinks and snacks normally get `meal_types: ["snack"]`. `difficulty`: easy = basic skills and few steps; hard = demanding
  technique or many stages.
- `line_estimates`: exactly one entry for every ingredient line whose
  `needs_amount` is true (such as "salt to taste" or "oil for frying"), with a
  realistic amount for the stated servings, a mass or volume unit from
  `g, kg, oz, lb, ml, l, tsp, tbsp, cup` (never a count), and a basis. For
  frying oil, estimate what is absorbed, not what is in the pan.
- `consumed_estimates` (optional, but required whenever it applies): for a line
  whose stated amount is mostly **not eaten** — oil for deep frying, water for
  boiling pasta or rice, a marinade or brine that is discarded — give the amount
  actually consumed by the whole recipe, e.g.
  `{"index": 16, "quantity": 3, "unit": "tbsp", "basis": "3 cups oil for deep frying; ~3 tbsp absorbed by 4 omelets"}`.
  Nutrition uses this amount; the recipe still shows the stated one.
- Every `evidence` and `confidence` field is required.

### Do not

- invent a source URL: a source must be a page you actually found;
- change a servings count the source states;
- read or use anything under the evaluation held-out folders;
- decide an allergen label (the opinion field is only compared).
