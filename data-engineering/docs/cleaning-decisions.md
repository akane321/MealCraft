# 清洗决策

## 为什么保留原始字符串

食材解析规则一定会更新。只保存清洗结果会失去复现和纠错能力，因此每条食材行必须保留 `original_text`。

## 为什么不直接相信 RecipeNLG NER

NER 是候选食材实体，不包含可靠数量、单位、处理方式或内部 ID。第一轮把 NER 用作解析对照，不把它当作最终标签。

## 数量和单位

- Unicode 分数转换为十进制。
- `1 1/2` 转换为 `1.5`。
- `1-1/2`、`2-3/4` 这类**连字符写的带分数混合数**转换为 `1.5`、`2.75`，不是区间。
  判据：连字符后面是分数（`\d+/\d+`）时按混合数处理；是整数（`2-3`）时按区间处理。
  真实 RecipeNLG 大量使用连字符混合数，20 行 synthetic fixture 没有覆盖，首轮 5,000 行 profiling 发现。
- `2-3` 保存为 `quantity_min=2`、`quantity_max=3`，不擅自取中点。
- 区间分隔符 `to` 只有在前后都有空格时才生效（`2 to 3`）。否则 `4 toasted buns`、`1 tomato`
  会因为词内的 `to` 被误判为区间。词数字（`a`、`one` 等）也要求词边界。
- `to taste`、`as needed` 等数量保持未知并进入复核提示。
- piece-to-gram 转换只有在来源可靠且具体食材匹配后才能执行。
- **大写 `T`（tablespoon）和小写 `t`（teaspoon）区分大小写解析**，因为二者相差 3 倍量——
  其余单位都不区分大小写，只有这一对例外。原始文本里的大小写在 `_clean_text` 统一转小写
  之前先读出来记住，避免被后续处理抹掉。人工复核发现 `T`/`t` 这个模式全样本有 66 处。

## 单位识别

- `units.csv` 覆盖质量、体积、计数（piece/slice/clove/stick/stalk/bunch/head/…）、
  包装（can/jar/bottle/box/bag/carton/container/package/pkg/envelope）和非正式（pinch/dash/drop）。
- 括号里的规格备注（`1 (8 oz.) can tomatoes`）在识别单位**之前**先剥离到 `preparation`，
  保证真正的单位（can）成为剩余文本的首词。
- 数字后面直接跟食材名、没有单位词时（`2 eggs`、`1 onion`），记为 `piece`（count 维度）。
  这是约定读法，不算缺单位，不进复核。

## 食材名称

归一化分两层：

1. 文本规范化：小写、空白和标点清理、剥离处理词和描述词。
   逗号分段时**先逐段剥描述词**，再选第一个还剩食材名的段做 `ingredient_text`，
   其余进 `preparation`——这样 `diced, cooked chicken`（描述词在前）不会被解析成空。
2. 语义映射：先精确查 `config/ingredient_aliases.csv`；不中再用去连字符 / 朴素单复数
   归一后重试一次。仍不中保留为 `candidate`，不得默认为已有食材。

只含备注、没有食材名 / 数量 / 单位的源行（`(see note)`、`OPTIONAL`、`_____`）
不算食材，从 curated 的 `ingredients` 里剔除（备注文本仍保留在 staging），
数量计入 `quality.warnings.dropped_note_lines`。绝不把某条食谱的最后一行剔成空。

`ambiguous_alternative` 检查整个逗号分段前的剩余文本，不只查最终选中的
`ingredient_text`——否则 `"beef, pork or chicken"` 这类写法，"or" 落在被丢进
`preparation` 的那一段里，标签会检测不到。人工复核样本里这类被漏标的有 125 处。

`config/ingredient_aliases.csv` 由 `scripts/build_ingredient_aliases.py` 生成，分两部分：
`TABLE`（作者手写、分组、带注释的基础映射）+ `REVIEWED_ADDITIONS`/`REVIEWED_ALIASES`
（人工复核包 `data/review/packet/` 的决定，逐条来自 `unmapped_high_freq`/`ner_mismatch_sample`
sheet 的 `decision` 列，来源可追溯）。当前覆盖约 448 个 canonical ID，把 5,000 行样本的
内部映射覆盖率从 25.85% 提到 **81.50%**。

描述词（`ground`、`whole`、`medium`、`fresh`、`unsalted`、`extra-virgin`、`cold`、`soft` 等）
按 preparation 处理，不产生新的食材身份（符合 ADR-0012）。有辨识意义的词**不**当描述词：
`green onion` ≠ `onion`。

复合短语（`salt and pepper` 及变体）按"明确复核规则"映射到显式的 composite ID
`ING_SALT_AND_PEPPER`，不强行拆到单一候选。

### 人工复核确认的具体判断（第一轮 180 条 unmapped + 120 条 ner_mismatch）

- `red pepper`（小剂量、tsp 计量）→ remap 到 `cayenne pepper`（辣椒粉），不是 bell pepper；
  `sweet red pepper`/`yellow pepper` 仍 remap 到 `bell pepper`。人工判断，非自动规则。
- `chocolate`（裸词）→ remap 到 `baking chocolate`（原 canonical_name 从
  "unsweetened baking chocolate" 改为通用的 "baking chocolate"，因为它现在也覆盖
  semisweet/bittersweet/plain）；`dark chocolate` 独立成 canonical，补 `milk` 过敏原，
  和 baking chocolate 保持一致假设。
- 裸词 `syrup` → 通用 canonical `syrup`（食材文本里 5 次出现只有 1 次写明是桃子糖浆，
  不能把"桃子"套到另外 4 次没提过的记录上）。
- `Cheez Whiz` → canonical 名改成通用的 `processed cheese sauce`，品牌词降级为别名——
  和 Crisco→shortening、Eagle Brand→sweetened condensed milk、Velveeta→american cheese
  的品牌处理惯例保持一致。
- **通用/未指定食材**（`meat`、`fruit`、`berries`、`broth`、`soup`）：抽查过全部出现，
  大部分是真实但字面就没说具体是什么的写法（不是解析错误），保留为通用 canonical。
  **下游不得用这些做硬约束过滤（过敏原/忌口）或精确 FairPrice 商品匹配**，只能用于
  存在性/数量统计。`soup`、`meatballs` 最初按"看起来像分节标题"被跳过，人工复核发现
  实际大部分出现是带数量的真实食材，已改为 add。
- `au jus mix` 从 `brown gravy mix` 里拆出来独立成 canonical（风味和稠度都不同）；
  `chicken bouillon`/`beef bouillon` 从对应的 broth 里拆出来并入 `bouillon cube`
  （浓缩块/粉和现成高汤的用量换算不是一回事）。
- `lime zest` 维持独立 canonical，不 remap 到 `lime`——和已有的 `lemon zest`
  （同样独立于 `lemon`）保持一致的颗粒度，因为果皮和果肉/果汁营养成分不同。

## 过敏原与膳食约束

第一轮只根据明确食材映射生成候选标签，例如 peanut → peanuts。复合食品、品牌食品和含糊词必须人工复核。MealCraft 不提供医学诊断或治疗建议。

## 营养值

只有同时满足以下条件才允许计算食谱营养：

1. 食材已经映射到明确的营养参考条目；
2. 数量可以可靠换算为质量或体积；
3. 份数已知；
4. 记录了营养数据版本、基准和计算方法。

因此 RecipeNLG 第一轮的大量记录会显示 `nutrition.status = not_computed`，这是正确的质量表达，不是程序失败。

