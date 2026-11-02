# MealCraft Data Engineering

本目录把大型但不完整的 RecipeNLG 原始食谱，转换成 MealCraft 可使用、可审计、可继续补充营养和
超市商品信息的数据层，并切出版本化 release。Release v2.1 已于 2026-09-21 导入，与原有的策展目录并存（见
`../docs/data/README.md` 第 2 节）；运行时目录文件仍是 `data/recipes/recipes.json`，当前进度见 `docs/current-status.md`。

核心原则：

1. 原始数据只读，清洗结果写入新的分层目录。
2. 原始值、解析值和修正值分开保存。
3. 缺失信息保持 `null`；任何补全（agent 或规则）都必须记录依据、置信度和被否决的备选
   （ADR-0024）。过敏原只由确定性规则判定。
4. 每条记录保留来源、许可、处理版本和置信度。
5. 食材库、食谱库、营养参考库和 FairPrice 商品库使用独立 ID，通过映射表连接。

## 版本化 release 与三个食材数

`data/release/<版本>/` 下每个 release 都带 `release_manifest.json`（计数、哈希、上游扫描量）
和 `quality_report.md`；release 一经发布不再修改，修正以新版本发布。

三个食材数量含义不同，都对：

- **规范食材词表**：`config/ingredient_aliases.csv` 中的全部 `ingredient_id`，即管道能识别的
  所有食材（营养映射在它上面做）；
- **release 中的食材**：某个 release 里实际被收录菜谱用到的那部分，记在该 release 的
  `release_manifest.json` 的 `released_ingredients`；
- 因此词表总数总是大于等于任一 release 的食材数；具体数值以文件为准，不在文档里复写。

## release v2 的收尾顺序

三份富化工作（A/B/C）交齐之后，按顺序跑：

```bash
python scripts/v2_packet.py merge          # 校验三份、合并、写 data/staging/v2_agreement.json
python scripts/build_release_v2.py         # 写 data/release/v2/（配额、克数、营养、过敏原、manifest）
python scripts/v2_audit_sample.py draw     # 抽样（默认 40 条菜谱 + 20 个食材，种子固定）
#   人工逐条复核，把判定写成 JSONL 喂回去：
python scripts/v2_audit_sample.py record < verdicts.jsonl
python scripts/v2_release_report.py        # 写 ATTRIBUTION.md 和 quality_report.md
```

## release v2.1：食材清单完整性与更严格的过敏原

v2 已发布、不再修改；`build_release_v2.py` 现在输出 `data/release/v2.1/`，比 v2 多三项检查：

```bash
python scripts/recipe_completeness.py packet --shards 8     # 标题或步骤提到、但食材清单里没有的过敏原食物 -> 逐条复核包
python scripts/recipe_completeness.py sample --size 300     # 未被标记的菜谱抽样，测漏检
python scripts/recipe_completeness.py validate FILE...
python scripts/recipe_completeness.py merge FILE...         # 写入 data/enrichment/completeness/v2_review.jsonl
python scripts/build_release_v2.py                          # 复核为 incomplete 的丢弃；未复核的被标记菜谱也丢弃
python scripts/v2_release_report.py
```

构建会把"被标记但没人复核过"的菜谱写到 `data/review/completeness/awaiting_review.jsonl`，
再跑一次 `packet` 就会打包它们。`config/allergen_corrections.csv` 是 owner 确认过的过敏原补充
（只增不减）；含鱼或贝类的食材、或标题步骤提到肉鱼，菜谱就不是素食/纯素。

## release v2.2：整件与容器的克数修正（owner 2026-10-23）

v2.1 已发布、不再修改。v2.1 无法从仓库重建（`build_release_v2.py` 读的 `data/staging/` 被 git 忽略），
所以 v2.2 由一个确定性的修正步骤从 v2.1 的已提交文件生成：

```bash
python scripts/correct_release_v22.py      # 读 data/release/v2.1/，写 data/release/v2.2/（含 corrections.jsonl）
PYTHONPATH=src python -m unittest discover -s tests -p "test_correct*"
```

只改这些行的克数（以及鲜红椒行的食材 id），再用构建时同一份 `nutrition_per_100g` 重算这些菜谱的每份营养；
菜谱集合、id 和其他字段不变。修正类别：鲜红椒误映射到 cayenne、行文本里写明但构建漏读的重量、
"N 件（总重）"被乘了 N、整鸡、整颗菜/整个菠萝、整张 pizza 饼底、千层面片。克数只来自行文本、同一食材条目
自己的单位重量，或带出处的公开参考（USDA FoodData Central，见脚本里的 `SOURCES`）。大小词（small/large）
不在本轮。每一行的前后克数和出处在 `data/release/v2.2/corrections.jsonl`，数量、守卫告警和未修的项目
在 `data/release/v2.2/quality_report.md` 末节。产品导入和基线评分从这一版起读 v2.2。

## data release v3：v2.2 原样 + 新增菜谱（Knowledge ADR-0103 第 3 节，issue #390）

"data release v3"是数据版本，不是名为 v3 的留出评测协议。产品从这一版起读 v3（Knowledge ADR-0111）：后端
`RELEASE_VERSION` 是 v3，导入 12,895 道里的 12,894 道（和 v2.2 一样跳过 `RCP2_5EFEFE98D566`）；v2.2 作为 v3 的冻结底本保留。

构建要用 `data/staging/` 里被 git 忽略的输入（只在有这份 staging 的机器上能重跑）：

```bash
python scripts/select_v3_candidates.py      # 第 1 步：从 v2_pool.jsonl 挑新候选 -> staging v3_selected.jsonl（约 45 秒）
python scripts/enrich_v3_openai.py --env-file ../.env --workers 8 --max-usd 25   # 第 2 步：OpenAI API 富化，可断点续跑
python scripts/build_release_v3.py          # 第 3 步：写 data/release/v3/（约 15 秒）
python scripts/build_release_v3.py --out DIR   # 同样的文件写到 DIR；两次运行逐字节相同
python -I -X utf8 scripts/manual_check.py draw --new     # 新增菜谱的 100 道人工抽检样本 -> docs/manual-check-20261103/
python -I -X utf8 scripts/allergen_review.py draw --new  # 新增菜谱的 50 道过敏原复核样本 -> docs/allergen-review-20261103/
PYTHONPATH=src python -m unittest discover -s tests -p "test_build_release_v3.py"
```

输入：已提交的 `data/release/v2.2/`；staging 的 `v2_enrich_set.jsonl`、`v2_merged.recipes.jsonl`、
`v2_merged.ingredients.jsonl`（v2 富化集，重建超配额菜谱）和 `v3_selected.jsonl`、`v3_merged.recipes.jsonl`、
`v3_enrich_failed.jsonl`（新候选）；`enrichment-work/part-*/recipes.input.jsonl`（v2 给富化者看的时长）。
每个输入的 sha256 记在 `release_manifest.json` 的 `derived_from`，`fingerprint` 覆盖 recipes.jsonl、
ingredients.jsonl 和去掉该字段的 manifest。

决定（owner 2026-11-02"直接做，中等质量也可以"，完整列表在 manifest 的 `change_notes` 和 `quality_report.md`）：

- v2.2 的每条记录逐字节复制（id、文字、字段都不变），`ingredients.jsonl` 就是 v2.2 的 701 个食材，不新增食材 id；
- 新增菜谱两条来源，都走 `build_release_v2.build_recipe` 的同一套规则，再套 v2.2 的克数修正
  （`correct_release_v22.correct_recipe`，对 v2.2 的食材形态称重，改动记在 `corrections.jsonl`）：
  v2.1 构建过但超配额没发布的菜谱，和 v2 从未选中、每行都已映射到 701 个食材、每个食材都能按规划器规则定价、
  分诊菜系不属于美国桶的 RecipeNLG 新候选（主菜优先）；
- 新候选用 OpenAI API（`gpt-5.4-mini`，推理强度 low）按 v2 同样的字段、词表、说明和校验富化，修订了 ADR-0030 用会话富化的做法；
- 不发布：用到 v2.2 以外食材 id 的、菜系 `international` 的（ADR-0034，不改标）、完整性标记了但没有复核结论的
  （不做新的完整性复核）、修正后每份热量不合理的、低于导入下限（2 行食材和 1 个步骤）的、标题（小写、空白归一）
  和已发布菜谱重复的（顺序：v2.2，再超配额，再新候选，各按 recipe_id）；
- 任何一个菜系标签不超过最终总数的 20%：超出时先留规划器能用的类别（main、side、soup、salad、breakfast，其余在后），
  同类按 recipe_id；名额按最终总数反复重算到不再变化；
- 总数是通过全部检查的数量，没有裁到 12,400；组合替代品（"half-and-half = 牛奶 + 奶油"）这一版不做，schema 没有字段。

每个没有发布的候选都在 `dropped.jsonl` 里，带原因。新增菜谱的人工抽检和过敏原复核只抽新增菜谱（种子 20261103），
"至少 95%"按点估计读，同时报告 Wilson 区间（issue #392）。

## 规划器可用池报告（每次发布、改价格或改标签之后重跑）

`quality_report.md` 只管 release 本身；发布出来的菜有多少真正进得了规划器、每道关挡掉多少，由下面这条命令生成
（在仓库根目录，离线）：

```bash
uv run --project backend python -m app.data.planning_pool   # 写 docs/planning-pool-report.md 和 .json
```

它把已提交的目录和 release 导进内存数据库，每道菜按规划池的关（`RecipeRepository._load_for_planning`：
菜的类别、每种食材都有价格、没被撤下、`recipe_quality.incomplete` 判断完整）走一遍，再过结构化规划器的角色关
（`meal_composition.meal_role_of`）；被挡的菜只记在它没过的第一道关下面。能用的菜分"能排午餐、晚餐"和"能排早餐"两项
（一天排三餐，ADR-0070）。报告还单独数新加坡、马来西亚菜（`malaysian_singaporean`）进了多少，列出最常用的没定价食材，
以及给前 N 种定价后能多进多少道菜（上限）。报告头记 release 版本和指纹、标签文件和可定价食材集合的 SHA-256。数字只看报告本身，
不在文档里复写。

## release v2 的 FairPrice 商品映射

```bash
python scripts/capture_fairprice_snapshot.py               # 每个食材搜一次 FairPrice，原始结果写入 data/enrichment/fairprice/v2/observations.jsonl
python scripts/fairprice_mapping.py packet --shards 8      # 按食材打包候选商品，供逐条判断（data/review/，不提交）
python scripts/fairprice_mapping.py validate FILE...       # 检查提议：商品必须来自该食材的搜索结果、包装克数和依据齐全
python scripts/fairprice_mapping.py merge FILE...          # 合并进 mapping.jsonl，review_status 为 proposed
python scripts/capture_fairprice_snapshot.py --follow-ups 2  # 用提议里的 search_again 再搜一轮
python scripts/fairprice_mapping.py packet --unavailable   # 只重新打包仍不可用的食材
python scripts/fairprice_mapping.py sample --size 40       # 抽查样本，种子固定
python scripts/fairprice_mapping.py record VERDICTS.jsonl  # 记录 owner 的判定
python scripts/fairprice_mapping.py export                 # 写运行时快照 ../data/products/fairprice-v2-snapshot.json
```

抓取请求间隔 3 秒，连续失败 3 次就停，可断点续跑。映射由 AI 提议，抽查前都是
`proposed`；导出时不收录不可用、被 owner 判为需修正、以及置信度低于 0.6 的映射。

`v2_audit_sample.py` 的抽样种子固定，所以同一个种子永远抽到同一批；
抽样工作表是生成物（`data/review/`，不提交），判定结果是人的判断，提交在
`docs/v2-sampled-audit.json`。抽查是 `ADR-0024` 第 2 节的要求：AI 富化允许，
条件是事后抽样审计。抽查可以在 A/B/C 没交齐时就先跑，工作表会记录当时包含了哪几份。

## Cold Storage 商品映射（第二家零售商）

只给 FairPrice 快照里没有的 v2.2 食材找 Cold Storage 商品（`docs/design/cold-storage.md`）：

```bash
python scripts/capture_cold_storage_snapshot.py             # 搜 search_again 文本再搜规范名，每个食材最多 3 次，写 data/enrichment/cold_storage/v1/observations.jsonl
python scripts/capture_cold_storage_snapshot.py --follow-up --limit 400  # 第二轮：还没有 mapped 行的食材，换规范名、简化叫法、search_again 再搜，每个食材最多 3 个新查询
python scripts/cold_storage_mapping.py packet --shards 3    # 打包候选商品（data/review/cold_storage/batch<i>.jsonl，不提交）
python scripts/cold_storage_mapping.py validate FILE...     # 检查提议，规则同 FairPrice（没有 not_purchased）
python scripts/cold_storage_mapping.py merge FILE...        # 合并进 data/enrichment/cold_storage/v1/mapping.jsonl
python scripts/cold_storage_mapping.py sample --size 40     # 抽查样本，种子固定
python scripts/cold_storage_mapping.py record VERDICTS.jsonl  # 记录 owner 的判定，写 docs/cold-storage-v1-sampled-review.json
python scripts/cold_storage_mapping.py export               # 写运行时快照 ../data/products/cold-storage-v1-snapshot.json
```

只用标准库的公开 GET：每秒最多 1 次、单次最多 600 次，遇到第一个非 200 或不认识的页面（含验证码）就停。
商品列表在页面的 Next.js flight 数据（`self.__next_f.push` 的字符串拼起来）里 `"initialProducts":` 之后。
按重量卖的商品价格是每公斤价，导出的整包价是 `round(促销价 × averageWeight, 2)`。`external_id` 是 `cs-<productId>`。

## RedMart 商品映射（第三家零售商）

只给 FairPrice 和 Cold Storage 快照都没有的 v2.2 食材找 RedMart（Lazada 新加坡的超市）商品（`docs/design/redmart.md`）：

```bash
python scripts/capture_redmart_snapshot.py             # 规范名、简化叫法、两家的 search_again，每个食材最多 3 次，写 data/enrichment/redmart/v1/observations.jsonl
python scripts/redmart_mapping.py packet --shards 3    # 只打包有 RedMart 候选的食材（data/review/redmart/batch<i>.jsonl，不提交）
python scripts/redmart_mapping.py validate FILE...     # 检查提议，规则同 Cold Storage
python scripts/redmart_mapping.py merge FILE...        # 合并进 data/enrichment/redmart/v1/mapping.jsonl
python scripts/redmart_mapping.py sample --size 40     # 抽查样本，种子 20261101
python scripts/redmart_mapping.py record VERDICTS.jsonl  # 记录 owner 的判定，写 docs/redmart-v1-sampled-review.json
python scripts/redmart_mapping.py export               # 写运行时快照 ../data/products/redmart-v1-snapshot.json
```

只用标准库的公开 GET，只访问 `https://www.lazada.sg/tag/<slug>/?ajax=true&q=<query>&page=<n>` 这一个搜索接口（返回 JSON，
商品在 `mods.listItems`）：每秒最多 1 次、单次最多 500 次，遇到第一个非 200、重定向（含登录）或不认识的响应（含 punish/captcha/x5sec 页面）就停，
不绕过任何限制（ADR-0110）。搜索覆盖整个 Lazada，只保留 `sellerName == "RedMart"`（或 `sellerId` 为 `1000008313`、或带 `Redmart` 图标）的商品；
第 1 页没有 RedMart 商品且结果多于一页时才读第 2 页。包装规格只在商品名里，价格取列表价 `price`。`external_id` 是 `rm-<itemId>`，
`product_url` 是 `https:` 加 `itemUrl`。

## 手工录入价格（最后一层）

FairPrice、Cold Storage、RedMart 都没有的食材，由人从 Shopee、Lazada、Amazon 等平台查价后填表（`docs/design/manual-prices.md`）：

```bash
python scripts/manual_prices.py validate SHEET   # 逐行检查，按 rank 列出全部问题；有问题时退出码为 1
python scripts/manual_prices.py export SHEET     # 全部通过才写运行时快照 ../data/products/manual-v1-snapshot.json
```

表为 `data/enrichment/manual/v1/price-sheet.csv`（UTF-8 带 BOM，Excel 可直接打开；CRLF 也能读）。没填任何字段的行视为空行；同一食材有多个商品就重复该行。
价格可以写成 `4.5`、`S$4.50`，必须为正且精确到分；链接的域名要属于所填平台（`other` 不限；`redmart` 接受 `redmart.lazada.sg` 与 `lazada.sg`）；日期不能晚于新加坡今天。
包装克数：`g`/`kg` 直接换算；`ml`/`l` 用发布版食材记录自带的每毫升克数，没有就按 1.0 g/ml 并在 `package_grams_basis` 里注明（v2.2 目前没有这个字段，所以都是 1.0）；
`count` 用发布版该食材的 `piece` 单件克重，没有就拒绝该行。`external_id` 是 `mn-<rank>-<n>`，`fetched_at` 是 `observed_date` 的新加坡零点，每个商品都是 `owner_recorded`。

## 菜谱与食材标签 v1 的抽检（Reviewing recipe and ingredient tags）

### 规则修复与原审查分开

`docs/recipe-tags-v1-sample.json` 是原批次的固定审查包，标签重生成不覆盖它。
已审核字段、AI建议和待定项不能混作完整人工准确率，更正建议也不等于原预测正确。
失败模型批次的关键字段在仅规则重生成时一直受未审核门禁约束：现行规则能定的写规则值、记入复核批次
（owner 2026-10-24，见下文），规则留空的保持原值和原来源；不会因为新规则可以给出答案就自动放行。
`--accept-batch` 是独立且须获准的操作。

规则只采用食材行有依据的肉种（包括括号内说明）；泛称肉、不同肉类共用一个总重的主要来源比例保留未知。
具体食材后的替代说明不算第二种实际肉类；真正的“A或B”仍保留未知。
菜名点名的畜禽肉实际低于主要来源门槛时也保留未知；少量海鲜配料不套用这条规则，但过敏原照常保留。
“主要来源未知”不抹掉已经确定的餐食角色；组合规划的入选检查另行挡住来源仍未知的主菜，不能将未知当作没有蛋白或来源不重复。
候选投影、角色入选和最终验证共用该判断，混合菜类与结构化餐次的周计划也不能绕过。
标题可发现缺料，不能补出缺失的肉或数量。标签器与规划器共享缺肉检查；这样的菜不进入规划。
Steak并不专指牛肉；列明的其他肉类或豆腐可以支持它。标题明确提供替代肉类时，只要求其中一种有实际食材依据。
主食以克重构成为依据，完整馅饼的面皮计入，肉馅黏合料和炸衣不自动计入；
三明治或汉堡实际列出面包载体就属于自带主食的餐，不受面包占比门槛限制；豆类不当谷物主食。
熟重按计量口径识别：体积单位的熟米面不再膨胀；质量单位后面的“cooked and drained”仍按干重换算。
有两种单位时以先给出的计量单位为准。烤制、焗制不是正餐角色的充分条件，
馅料和配料本身则是 `sauce` 部件，不单独成餐。
原始菜类写成配菜的米饭菜式，只有实际米饭克重占比达到现有主食载体门槛时才判为主食或完整餐食，
不会只凭菜名或降低全局门槛补判。仿蟹肉保留食材库的鱼类身份，不因原文含 `crab` 就改成真蟹。
人工核实的原料与步骤冲突由标签器和规划器共用排除记录，源资料修正并复核前不参与规划；
明确的汤类身份不必因此抹掉，但其主要蛋白来源保留未知。

改完规则后，另生成[变动菜谱复核包](docs/recipe-tags-v1-rule-changes-review.md)：

```bash
python data-engineering/scripts/review_tag_rule_changes.py --base-ref <修复前的提交> --count 25
```

包中包含原标签、新标签、变动字段、完整步骤与release归一化克重。已知回归案例优先，
其余按固定种子从变动菜谱抽取；这证明修复的针对性，不是独立总体准确率。
模型字段仍被门禁拦截时会明确标出，新规则建议不能被误读为已放行。
注意：这是带日期的复核包，只能在它自己的 base 修订上复现；脚本的"冻结"判断只认 `llm`，
不适用于复核批次 `recipe-tags-v1/review-table-20261024` 之后的标签文件（在其后重跑会断言失败或写出缩水的包）。
同样带日期、同样只能在各自 base 上复现的还有 `data-engineering/scripts/role_review_table.py`（[role-rules-20261023b](docs/role-rules-20261023b/README.md)）
和 `data-engineering/scripts/role_rules_review.py`（[role-rules-119-20261023](docs/role-rules-119-20261023/README.md)）。

人工核验完成后，原包的 `before`、`after` 和标签哈希保留为当时的快照；
不同意的字段记为 `verdict=false`，人工正确值另存 `corrected_values`，不覆盖原预测。
后续计量政策改变既有判断时，落实报告单列原人工值、当前口径值及修订依据；
原审查包不改写，也不声称受修订影响的字段已在新口径下再次获得人工核验。
落实修正后运行：

```bash
python data-engineering/scripts/review_tag_rule_changes.py --base-ref <修复前的提交> --verify-owner-review
```

该命令逐字段验证当前标签与人工意见一致，生成[修正落实报告](docs/recipe-tags-v1-rule-changes-review-applied.md)，
同时刷新获准的满血默认开发集前后对照；不重抽样、不覆盖审查包、不计算全库准确率、不放行模型批次。
它同样只能在该复核包的 base 修订上复现，不适用于复核批次之后的标签文件。

```bash
uv run --project backend python -m app.data.recipe_tags          # 只用规则；之前模型给的答案保留并复用
uv run --project backend python -m app.data.recipe_tags --llm    # 规则定不了的再问模型，默认花费上限约 US$5
```

规则在 `backend/app/data/recipe_tags.py`，产出 `data/recipes/recipe-tags-v1.json` 和
`data/ingredients/ingredient-tags-v1.json`，导入器（版本 6）按 release < 标签文件 < 运行时写入的顺序
写进数据库。覆盖率和模型花费见 `docs/recipe-tags-v1-report.md`。`--reask` 丢掉之前模型的答案重新问；
它同时撤销冻结，规则能定的冻结字段会直接放行，不经过复核批次。
运行时写入的菜谱标签会在重新导入时保留，前提是写入方把它标出来：删掉该字段在 `estimated` 里的条目（人定的值不是估计），
或把条目的 `reviewed` 设为 `true`。

抽检包是 `docs/recipe-tags-v1-sample.json`（种子固定）：按正餐角色和判定方式（rule、llm、未定）分层抽了
100 多道菜，另有全部"易坏"食材、全部基础调料和一些随机食材。owner 的做法：

逐条审查可使用 [标签审查表](docs/recipe-tags-v1-review.md)。表中标为 AI 建议的判定只是人工复核的起点，
不是已完成的人审或批次放行；确认时保留建议出处，并记录人工确认的条目、字段及修改。

1. 每道菜看 `tags`，在 `verdict` 里逐项填 `true`（对）或 `false`（错）；错的在 `note` 写正确值。
   值为 `null` 的项（规则和模型都没定）可以只在 `note` 里写应该是什么。
2. 每个食材填 `verdict.perishable` 和 `verdict.basic_seasoning`。按 `ADR-0068`，"易坏"为 `true` 的
   每一项都要人工确认，所以抽检包收录了全部易坏食材。
3. 每道菜的 `why` 说明它为什么被抽中。两个必审分层在规划器读这些值之前要先审完：`llm protein_sources`
   （模型给的蛋白来源，它会喂给"同一餐蛋白不重复"的硬规则）和 `hearty salad`（不是蔬菜主导、带主蛋白的沙拉；
   标成 `salad` 后它只能当蔬菜菜，而蔬菜主导检查又不让它当，所以哪个位置都填不了。owner 2026-10-19 决定：带肉的沙拉不算主菜，
   保持这样）。模型定的值（`estimated` 里 `method` 为 `llm`）在本批抽检审完前，规划器不读。
4. 提交填好的文件。重跑标签命令时，已有判定的抽检包不会被覆盖。正餐角色的准确率按
   `meal_role` 判定为 `true` 的比例计算，写进报告（`08-household.md` 第 0.9 节）。
5. 抽检通过后接受这一批模型的值：

   ```bash
   uv run --project backend python -m app.data.recipe_tags --accept-batch recipe-tags-v1/llm
   ```

   它把标签文件里这一批 `method` 为 `llm` 的条目全部设为 `reviewed: true`（规则的值不动），导入器再把它带进数据库。
   在此之前，`meal_role`、`contains_staple` 或 `protein_sources` 里有一项是模型定的、还没 `reviewed` 的菜，
   结构化规划（按 `meal_roles` 的餐）当它没打标签，哪个正餐角色都不填；按菜类（courses）的旧规划不受影响。
   重跑标签命令时，值没变的条目保持 `reviewed`，值变了的回到待审。

按 owner 2026-10-24 的决定，冻结批次由复核批次 `recipe-tags-v1/review-table-20261024` 接替，分两部分：
复核人复核表里的值（只导入规则留空的字段，仍是未复核的 AI 估计），和现行规则已能定的冻结字段（写规则值）。
两部分都等待接受，规划器在此之前不读；复核人亲自核对两部分的分层抽样、公开准确率后，owner 才决定是否
`--accept-batch recipe-tags-v1/review-table-20261024`。owner 逐道决定的五道菜的角色（`OWNER_ROLES`）立即生效，覆盖规则。
见 [复核批次](docs/review-table-20261024/README.md)。

数据版本 v3 新增的菜（v2.2 没有的 3927 道，ADR-0111）另有一批模型值：规则留空的字段由模型估计，记在批次
`recipe-tags-v1/llm-v3-20261103`（`V3_LLM_BATCH`），未复核、规划器不读。`--llm` 只问这些新菜；v2.2 的条目不动。
接受前由复核人亲自核对固定种子的抽样（`data-engineering/scripts/v3_tag_sample.py`，
[抽样说明](docs/tag-sample-20261103/README.md)），再由 owner 决定
`--accept-batch recipe-tags-v1/llm-v3-20261103`；它不影响冻结的 `recipe-tags-v1/llm` 批次。

面团、饼底、面糊、酱、腌料、干料、沙拉汁、肉汁、高汤、酱料膏和调味料这类"菜的一部分"由规则判成 `sauce`
（`sauce` 即所有不能单独成菜的部分），永远不填一餐：标题去掉括号、结尾的 `Recipe`/`I`/`II` 和 ` - ...`、
` for ...` 之后，最后一个名词是这类词，且它前面没有 `with`、`in`、`on`、`over`（酱汁类还要没有 `and`/`&`/`'n`）；
括号里是面团、饼底或面糊（`(Batter)`、`(Empanada Dough)`）也算。配菜里的 dressing 是填馅，仍是菜。
`Chicken In Tarragon Sauce`、`Cauliflower Crust Pizza`、`Meatballs For Spaghetti Sauce` 仍是菜。

## 目录

```text
data-engineering/
├── config/                    # 可审查的单位、别名、过敏原规则
├── data/
│   ├── fixtures/              # 可公开的 synthetic 脏数据
│   ├── raw/                   # 本地原始数据，不提交 Git（只有 raw_manifest.json 提交）
│   ├── staging/               # 解析后的中间结果（生成物，不提交）
│   ├── curated/               # 清洗产出（生成物，不提交）
│   ├── review/                # 复核与抽查队列（生成物，不提交）
│   ├── reference/             # USDA/FoodOn 等参考源
│   ├── enrichment/            # 富化结果，如营养映射（提交）
│   └── release/               # 版本化 release（提交）
├── docs/                      # 决定、数据字典、schema 冻结、富化进度
├── schemas/                   # JSON Schema 数据契约
├── scripts/                   # 发布、富化、流式校验脚本
├── src/mealcraft_data/        # 清洗实现
├── tests/                     # 单元测试
└── reports/                   # 质量报告和运行清单（生成物，不提交）
```

## 先跑通 synthetic 示例

无需安装第三方 Python 包：

```powershell
./scripts/run_demo.ps1
```

等价的手动命令：

```powershell
python -m mealcraft_data.cli run `
  --input data/fixtures/recipenlg_demo.csv `
  --sample-size 20 `
  --seed 5105
```

如果没有执行可编辑安装，可使用：

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m mealcraft_data.cli run --input data/fixtures/recipenlg_demo.csv --sample-size 20 --seed 5105
```

生成：

- `data/staging/recipes.parsed.jsonl`
- `data/curated/recipes.jsonl`
- `data/curated/ingredients.jsonl`
- `data/review/ingredient_review_queue.csv`
- `data/review/recipe_review_queue.csv`
- `reports/latest.json`
- `reports/latest.md`
- `reports/run_manifest.json`

## 使用真实 RecipeNLG

RecipeNLG 需要研究者本人阅读并接受使用条款。下载后，把 `full_dataset.csv` 放在：

```text
data/raw/recipenlg/full_dataset.csv
```

验证官方公布的压缩包 MD5（针对 `dataset.zip`）：

```powershell
Get-FileHash .\dataset.zip -Algorithm MD5
```

预期值：`3A168DFD0912BB034225619B3586CE76`。

随后运行固定随机种子的 5,000 条抽样：

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m mealcraft_data.cli run `
  --input data/raw/recipenlg/full_dataset.csv `
  --sample-size 5000 `
  --seed 5105 `
  --source-filter Gathered `
  --review-limit 200
```

## 下载开放参考数据

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m mealcraft_data.cli fetch-foodon
python -m mealcraft_data.cli match-foodon `
  --ingredients data/curated/ingredients.jsonl
python -m mealcraft_data.cli fetch-usda-foundation
python -m mealcraft_data.cli match-usda-foundation `
  --ingredients data/curated/ingredients.jsonl
```

USDA FoodData Central API 需要 `data.gov` API key；也可以先用限额较低的 `DEMO_KEY`：

```powershell
$env:FDC_API_KEY = "DEMO_KEY"
python -m mealcraft_data.cli enrich-usda `
  --ingredients data/curated/ingredients.jsonl `
  --limit 25
```

API key 只能放在环境变量中，不得写入数据文件、代码或 Git。

批量工作优先使用 `fetch-usda-foundation` 下载的版本化 CSV；API 用于少量候选核查。`enrich-usda` 默认跳过尚未经过内部归一化的 `candidate` 食材，避免浪费配额和放大错误。

## 验证

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m unittest discover -s tests -v
python -m mealcraft_data.cli validate --recipes data/curated/recipes.jsonl --ingredients data/curated/ingredients.jsonl
```

完整字段解释、来源边界和质量门槛见：

- [数据字典](docs/data-dictionary.md)
- [清洗决策](docs/cleaning-decisions.md)
- [来源与许可](docs/sources-and-licenses.md)
- [人工复核指南](docs/review-guide.md)
- [数据库组员操作流程](docs/team-workflow.md)
