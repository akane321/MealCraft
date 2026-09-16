# RecipeNLG 5,000-row profiling 与首轮覆盖率扩充

> 任务清单 #3（profiling）+ 覆盖率扩充。固定抽样，用于冻结 schema、词表和覆盖率阈值之前的现实评估。
> 结果是 prototype evidence，不是 release，也不是最终阈值。

## 运行参数

| 项 | 值 |
| --- | --- |
| 输入 | `data/raw/recipenlg/full_dataset.csv` |
| 输入 SHA-256 | `f376ee0bb9f99f323761abf6270d453f4eff2002c3625d04cabcf8b57dca0803` |
| 来源 | RecipeNLG 完整版（经 Kaggle 镜像 `saldenisov/recipenlg` 获取），2,231,142 条 |
| 抽样 | `--sample-size 5000 --seed 5105 --source-filter Gathered`（reservoir sample） |
| `Gathered` 母体 | 1,643,098 条 |
| pipeline 版本 | `mealcraft-data-cleaning/0.1.0`，schema `mealcraft.recipe.v1` |
| 复现性 | 连续两次运行产物 SHA-256 完全一致 |

## 产物

| 文件 | 首轮行数 | 扩充后行数 |
| --- | --- | --- |
| `data/staging/recipes.parsed.jsonl` | 5,000 | 5,000 |
| `data/curated/recipes.jsonl` | 5,000 | 5,000 |
| `data/curated/ingredients.jsonl` | 9,731 | 7,540 |
| `data/review/ingredient_review_queue.csv` | 200 | 200 |
| `data/review/recipe_review_queue.csv` | 200 | 200 |

食材记录数下降是因为同一食材的多种写法现在收敛到同一 canonical ID。

## 覆盖率（分母 = 43,163 个食材出现）

首轮 profiling → 覆盖率扩充后（同一固定样本，仅改 config + parser，未改抽样）：

| 指标 | 首轮 | 机械扩充后 | 人工复核应用后 | 说明 |
| --- | --- | --- | --- | --- |
| 内部映射 mapped | 25.85% | 79.11% | **81.50%** | `mapping_coverage_at_least_0_50` 门 FAIL → PASS |
| candidate（未映射） | 73.9% | 20.9% | 18.5% | 长尾主要是 section header、品牌名残留、真正歧义词 |
| unresolved | 0.24% | 0.02% | 0.02% | 解析后为空（10 条，note-only 行已单独剔除） |
| 有数量 | 92.08% | 92.15% | **92.15%** | 基本不变——缺的是源数据里就没写量 |
| 可识别单位 | 69.02% | 92.27% | **92.27%** | 加包装/计数单位 + "裸数字=piece" + 先剥括号规格 |
| 计算出营养的食谱 | 0 / 5,000 | 0 / 5,000 | 0 / 5,000 | 结构性，见下 |

"人工复核应用后"这一列来自 `data/review/packet/01_unmapped_high_freq.csv`（180 条，人工判断
add/skip/remap）+ `05_ner_mismatch_sample.csv`（120 条，人工确认/纠正映射）两个 sheet 的复核
结果，经二次审计（见 `docs/cleaning-decisions.md` 的"人工复核确认的具体判断"一节，共发现并
修正了 soup/meatballs 误判 skip、chocolate 拆分、syrup 过度具体化等 6 处问题）后应用。
`ambiguous_alternative` 复核原因从 1,366 → 1,596（"beef, pork or chicken" 类丢失的 "or"
语义被找回，125 处）。20 → 22 个单元测试全绿，产物确定性通过。

### 扩充做了什么

- `config/units.csv`：补齐 can/jar/bottle/box/bag/carton/container/pkg/envelope 包装单位，
  stick/stalk/bunch/head/loaf/sprig 计数单位，pint/quart/gallon，`lbs`。
- `config/preparation_terms.txt`：补描述词（ground/whole/medium/fresh/unsalted/extra-virgin/cold/soft…），
  这些不产生新食材身份。
- `config/ingredient_aliases.csv`：由 `scripts/build_ingredient_aliases.py` 的分组映射表生成，
  约 400 个 canonical ID / 1,650 条别名，覆盖样本高频食材。
- parser：括号规格备注在识别单位前剥离；裸计数记为 `piece`；精确匹配不中时用
  去连字符 / 朴素单复数归一重试一次；修 `extra-virgin` 剥词后遗留的 ` - ` 碎片。
- parser（第二轮）：逗号分段先逐段剥描述词再选食材名——修 `diced, cooked chicken`
  这类"描述词在前"被解析成空的 bug（`empty_after_parsing` 117 → 10）；纯备注行
  （`(see note)`、`OPTIONAL`、`_____`）不再当食材行，计入 `quality.warnings.dropped_note_lines`；
  `_remove_phrase` 正则改为 lru_cache 预编译（管道 5min → 50s）。
- 20 个单元测试全绿；连续两次运行产物 SHA-256 一致。

### 人工复核包

`scripts/build_review_packet.py` 从 curated 输出生成分层复核包
`data/review/MealCraft_review_packet.xlsx`（6 个 sheet：未映射高频 / or 歧义 /
复合词 / 安全过敏原 / NER 不一致 / 空解析行），每行一个决定，带 first-pass 建议
和留空的复核列。安全过敏原表建议两人复核。

## 复核原因分布

| 原因 | 首轮 | 扩充后 |
| --- | --- | --- |
| `unmapped_ingredient` | 31,901 | 9,702 |
| `unit_missing_or_unknown` | 8,311 | 156 |
| `missing_quantity` | 3,415 | 3,396 |
| `ner_mismatch` | 1,755 | 1,761 |
| `ambiguous_alternative`（含 "or"） | 1,359 | 1,359 |
| `quantity_range` | 636 | 576 |
| `informal_quantity`（to taste 等） | 312 | 312 |
| `empty_after_parsing` | 101 | 117 |
| `empty_ingredient` | 4 | 13 |

## 解析器缺陷（本轮发现并已修复）

真实数据触发了两个 20 行 synthetic fixture 没有覆盖的 bug：

1. **`2-1/2` 被误读成 `2` 到 `1/2` 的区间。** RecipeNLG 大量使用连字符写带分数混合数（`1-1/2 teaspoons`、`2-3/4 cups`）。
   之前 `2-1/2 cups` → `quantity_min=2, quantity_max=0.5`。修复后识别 `\d+-\d+/\d+` 为单个混合数；
   `\d+-\d+`（无斜杠）仍作为区间。
2. **`4 toasted buns` 里的 `to` 被当成区间分隔符。** 分隔符 `to` 会匹配到 `toasted`、`tomato` 等词内部，
   再加上词数字 `a`/`an` 无边界匹配，导致 `4` 到 `a`（=1）的假区间。修复后 `to` 只有前后有空格才算分隔符，
   词数字要求词边界。

影响：`quantity_range` 从 880 → 636（约 240 个假区间消除），`validate` 从约 240 个
`quantity_min exceeds quantity_max` 错误 → **0 错误**。测试从 11 → 20 全绿。

## 结构性缺口（不是 bug，是来源限制）

- **无 servings、无烹饪时间。** 5,000 条里 0 条带份量或时间字段。ADR-0012 要求营养计算同时满足
  "食材映射 + 数量可换算 + 份数已知"，因此本样本**整体无法计算食谱营养**，`nutrition.status` 全部
  `not_computed` 是正确表达。份量需要单独来源（例如从 directions 文本抽取 "serves 6"，或人工复核）。
- **无 cuisine / meal type / method / equipment / difficulty**。这些高维字段在启用对应偏好指标前
  需要受控词表和足够覆盖，本轮全空。
- **`Gathered` 子集以美式家常菜为主**，单位以 cup/tsp/tbsp 计量为主（见下），公制极少。

## 剩余未映射（扩充后 top，共 9,702 次 / 22.5%）

```
75 red pepper*        19 pkg. cream cheese**   14 filling / topping / sauce / cake***
14 meat               11 mashed potatoes       10 dark chocolate
10 1 lemon****         9  almond flour          9  oreo cookies
```

* `red pepper` 故意不映射：小写量级时多指辣椒粉，大块时指甜椒，歧义交人工判。
** `1 8-oz. pkg. cream cheese` 这类"数字-单位形容词-包装词"结构 parser 还没拆，量约几百。
*** `filling` / `topping` / `sauce` / `ingredients` 是菜谱的分节标题，不是食材，应单独标记。
**** `juice of 1 lemon` 里 "juice of" 被剥掉后剩 `1 lemon`。

映射天花板：在"精确别名 + 不 fuzzy 猜"的约束下，本样本约 78-82%。再往上要么补几百条长尾别名
（收益递减、错误风险上升），要么做模糊匹配（ADR-0012 禁止当作自动事实）。**77% 是可审计的合理结果。**

## 结构性缺口：营养

`nutrition_computed = 0` 无法靠清洗提升。需要三件目前都没有的东西：

1. 每条食谱的 **servings**（RecipeNLG 完全没有；可尝试从 directions 文本抽 "serves N" / "makes N"）；
2. 食材的 **克重换算**（piece→g、cup→g 按具体食材密度，需 USDA `food_portion` + 可靠来源）；
3. 食材到 **营养参考条目** 的已复核映射（USDA FDC）。

这是 R12 的独立子任务，不属于"数据清洗"本身。

## 尚未做（任务清单 #4 及以后）

- 对 ≥200 个问题项做分层人工复核（别名 / 单位 / 复合食材 / 缺份量 / 安全项）。
- 根据真实 profile 冻结 schema v1、单位词表、ID 规则、unknown 语义、release 覆盖率阈值。
- 补 canonical 别名后重跑并对比覆盖率与错误样本。
