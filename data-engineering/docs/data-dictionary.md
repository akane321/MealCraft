# MealCraft 食材库与食谱库数据字典

## Recipe

| 字段 | 含义 | 第一轮来源 |
|---|---|---|
| `recipe_id` | MealCraft 稳定食谱 ID | 对规范化内容计算 SHA-256 |
| `title` | 原始菜名 | RecipeNLG |
| `language` | 记录语言 | 第一轮固定为 `en`，来自数据集说明 |
| `source` | 原始数据子来源 | RecipeNLG `source` |
| `source_url` | 原食谱链接 | RecipeNLG `link` |
| `source_license` | 使用边界 | RecipeNLG research/education terms |
| `schema_version` | MealCraft 数据契约版本 | 管道常量 |
| `servings` | 份数 | RecipeNLG 无专门字段，从步骤文本里的"Serves N."/"Makes N servings."保守抽取；抽不出时保持 `null`，绝不猜测 |
| `servings_basis` | 份数的确定程度 | `stated_exact`（原文明说一个数）/ `range_lower_bound`（原文给的是区间如"Serves 10 to 12"，取下界作保守估计）/ `null`（`servings` 为空） |
| `prep_minutes` / `cook_minutes` | 时间 | RecipeNLG 不提供，保持 `null` |
| `ingredients` | 结构化食材行 | 本管道解析和映射 |
| `instructions` | 有序步骤 | RecipeNLG `directions` |
| `nutrition` | 每份营养及其来源 | 第一轮保持未计算，等待可靠份量和营养映射 |
| `quality` | 完整度、警告和复核状态 | 本管道计算 |

## Ingredient occurrence

| 字段 | 含义 |
|---|---|
| `original_text` | 不可修改的原始食材字符串 |
| `quantity_min` / `quantity_max` | 解析后的数量或范围 |
| `unit_raw` | 原始单位文本 |
| `unit_normalized` | 标准单位代码，例如 `g`、`ml`、`tbsp` |
| `ingredient_text` | 剥离数量、单位和处理词后的食材文本 |
| `canonical_ingredient_id` | MealCraft 内部食材 ID |
| `canonical_name` | 标准名称 |
| `preparation` | chopped、diced 等处理方式 |
| `optional` | 是否明确为可选 |
| `allergens` | 规则库明确识别的常见过敏原候选 |
| `normalization_status` | `mapped`、`candidate` 或 `unresolved` |
| `confidence` | 规则解析置信度，不能解释为事实正确率 |
| `review_reasons` | 进入人工复核队列的理由 |

## Canonical ingredient

| 字段 | 含义 |
|---|---|
| `ingredient_id` | 内部稳定 ID，例如 `ING_TOMATO` |
| `canonical_name` | 标准英文名称 |
| `aliases` | 当前规则库覆盖的别名 |
| `food_group` | 粗粒度食物类别 |
| `allergens` | 明确规则产生的过敏原候选 |
| `foodon_id` | 可选外部本体 ID |
| `fdc_id` | 经复核的 USDA 映射 ID |
| `nutrition_basis` | 例如 `per_100g` |
| `mapping_status` | 外部数据映射状态 |
| `provenance` | 来源和转换记录 |

## 缺失值规则

- 不知道的数值必须是 `null`，不能用 `0`。
- `0` 表示已经确认值为零。
- 未映射与不存在必须分开表达。
- 营养值必须同时带有基准、来源和完整度。

