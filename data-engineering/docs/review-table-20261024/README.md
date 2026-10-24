# 复核表导入批次 `recipe-tags-v1/review-table-20261024`（owner 2026-10-24）

复核人 liu-ub 为冻结的模型批次（`recipe-tags-v1/llm`，422 道菜）填了一份逐字段复核表。表里的决定是
AI 预填、在聊天里按"菜品类型"确认的，没有人逐行看过食材和步骤："已亲自核对（填 是）"一栏每一行都是空的。
所以这些值**不是人工复核**。owner 2026-10-24 选定 ADR-0076 的路线：

1. 只把现行规则留空的字段导入为一个 AI 估计批次，标为 `llm`、`reviewed: false`；
2. 现行规则已经给出的字段，以规则为准，不用表里的值；
3. 表里不在复核人可选角色范围内的值保持待定，不为此改规则；
4. 复核人亲自核对一份固定种子的 30 道抽样，公开这批的抽样准确率；
5. 之后由 owner 决定是否接受这一批（`--accept-batch`）。在那之前规划器不读这些值。

## 文件

- `decisions.json`：导入结果。`provenance` 记来源，`counts` 记数字，`accepted` 是导入的值（按菜），
  `skipped` 是每一个没导入的表格值及原因。由 `data-engineering/scripts/import_review_table.py` 生成，不要手改。
- `sample.json`：30 道抽样的抽取记录（种子、分层、每道菜导入的值）。
- `sample.xlsx`：给复核人亲自核对用的表（见下文"30 道抽样核对"）。
- 核对后由 `review_table_accuracy.py` 生成的 `accuracy.md` 和 `accuracy.json`（尚未生成）。

## 来源

| 项目 | 值 |
| --- | --- |
| 复核表 | liu-ub 的复核表（未提交进仓库），SHA-256 `ff85917c2821dc75c6f5e1f100191df4836309298574357fd246ad9327ed2095` |
| 读取的工作表 | `1 可用池277道`、`2 其余145道`（每行是一道菜的一个字段） |
| 行数 / 菜数 | 815 行 / 422 道，全部在复核包里 |
| 已亲自核对 | 0 行（该栏每一行都是空的） |
| 复核包 | `data-engineering/docs/role-rules-20261023b/review.json`，SHA-256 `d7dcb750eb57802419ce519816a8f8e813ca03d30d57432cfb4f11348f2248de` |
| 基准提交 | `5238449433d381af8a8304bb14d37713087b902a`（main） |

每行的取值按"你的决定"解读：同意 Claude 建议取建议值（去掉开头的"被规则挡住 →"），同意模型原值取模型值，
其他情况取"其他值"；聊天确认或被规则挡住而没有其他值的，取建议值；没有决定或"跳过"的不取值。
`staple（主食）`、`pork（猪）,beef（牛）`、`true（是）`、`null（未知/不放行）` 这类写法在第一个括号处截断。

## 导入规则与数字

一个字段只有在复核包里该字段的规则建议为 `null`（规则留给人定）时才可能导入：

- `meal_role`：必须在该菜的 `review_allowed_roles` 里；
- `contains_staple`：由导入的角色推出（`one_bowl`、`staple` 为 true，其他为 false），再和表里的值核对；
  不一致就两项都不导入。角色没导入，它也不导入；
- `protein_sources`：必须是词表里的来源（`PROTEIN_SOURCES`）或 `[]`，按词表顺序写入；
- 表里是 `null` 的字段保持待定，不导入。

| 字段 | 导入 | 规则已定且一致 | 规则已定但不同 | owner 逐道决定 | 超出可选角色 | 表里为 null |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `meal_role` | 106 | 172 | 45 | 2 | 16 | 28 |
| `contains_staple` | 106 | 181 | 36 | 2 | 16 | 28 |
| `protein_sources` | 2 | 18 | 7 | 0 | 0 | 50 |

原因码合计：`rule_decided_agrees` 371、`rule_decided_conflicts` 88、`owner_decided` 4、
`outside_allowed_roles` 32、`left_open` 106、`skipped_by_reviewer` 0、`staple_inconsistent` 0、`invalid_value` 0。
`contains_staple` 一行的"超出可选角色"和"表里为 null"跟随它的角色。

有导入值的菜共 108 道。导入的角色：staple 24、snack 24、sauce 24、dessert 20、soup 10、vegetable 2、
breakfast 1、one_bowl 1。导入的蛋白来源只有两道：Vietnamese Pâté Chaud（`pork`）和
Ramen Hot And Sour Soup（`egg`，原模型值为 pork、beef、shellfish、egg；食材里的肉是可选的未指明肉类）。

## 这些值仍是 AI 估计

`python -m app.data.recipe_tags` 读取 `decisions.json`，对冻结菜谱中规则留空的关键字段，用导入值替换冻结的模型值，
记为 `estimated.method = "llm"`、`batch = "recipe-tags-v1/review-table-20261024"`、`reviewed = false`。
构建时再按当前规则核对一次：当前规则已给出的字段不替换，角色也必须在当前 `review_roles` 里。
没有导入值的字段保持原来的冻结状态。

规划器（`meal_composition.unreviewed`、`product_path.recipe_tags`）把 `llm` 且未 `reviewed` 的
角色、主食、蛋白来源当作未打标签，所以这 108 道菜在接受之前和导入之前一样不进入结构化规划。
仅规则重生成之后重跑三份开发报告：full-default 和 household-rules 完全不变；shared-dish 的计划、份数、
采购额和达成率都不变，只有"可上桌菜谱"的池子计数少了 7（如 7567 → 7560、2041 → 2038）。这个计数直接读
菜谱行上的 `meal_role`，不经过复核门禁：导入值让 8 道冻结菜的角色移出正餐角色（其中 1 道是 Asian Wraps 的
owner 决定）、1 道移入。

## owner 2026-10-24 对六处聊天确认的逐条决定

这六处聊天确认与现行规则冲突。owner 在聊天中逐条决定：

| 菜 | 聊天确认 | 规则 | owner 决定 | 实现 |
| --- | --- | --- | --- | --- |
| Thai Sweet Potato Stew（`RCP2_66540AABF0E0`） | soup | staple | 按规则 staple | 导入时规则优先，不导入 |
| Sweet Potato & Pea Curry（`RCP2_F480AAE0C111`） | vegetable | staple | 按规则 staple | 同上 |
| Pupusas（`RCP2_3C310D373BB9`） | one_bowl | staple | 按规则 staple | 同上 |
| Recipe Of 1985'S Burleson County Kolache（`RCP2_24D1FD24F7F1`） | sauce | 留空；sauce 不在烘焙品的可选角色里 | 保持待定 | 超出可选角色，不导入 |
| Asian Wraps（`RCP2_A84B4E56257C`） | snack | protein_main | **例外：snack** | owner 逐道决定，覆盖规则 |
| Potato Croquettes With Parmesan（`RCP2_E5862A12458B`） | snack | staple | **例外：snack** | owner 逐道决定，覆盖规则 |

两处例外写在 `backend/app/data/recipe_tags.py` 的 `OWNER_ROLES` 里：`meal_role = snack`、`contains_staple = false`，
记为人的决定而不是 AI 估计（`method = "rule"`、`batch = "recipe-tags-v1/owner-20261024"`、`reviewed = true`），
所以规划器把它们当作已决定的 `snack`（小吃不填正餐）。`protein_sources` 不变，仍按规则
（Asian Wraps 为 `chicken`，Croquettes 为 `[]`）。其他菜不受影响。

注意：前三道"按规则 staple"的菜，在标签文件里仍是冻结的模型角色（未复核，规划器不读），因为仅规则重生成不放行
冻结批次里规则已能给出的字段（见 `data-engineering/README.md`"规则修复与原审查分开"）。规则的 staple
要等冻结批次的这些字段另行放行后才生效；若要现在生效，可以像两处例外一样把它们加进 `OWNER_ROLES`。

## 30 道抽样核对

`sample.json` 和 `sample.xlsx` 从 108 道有导入值的菜里，按种子 `20261024`、按导入的角色分层抽取 30 道
（每层至少 1 道，其余按层的大小分配）：staple 6、snack 6、sauce 6、dessert 5、soup 3、
breakfast 1、one_bowl 1、vegetable 1、只导入蛋白来源 1。`sample.xlsx` 每行是一道菜的一个导入字段（59 行），
列出编号、菜名、类别、带克重和原文的食材、前 400 字的步骤、导入值和可选角色。

复核人本人逐行核对：先看食材和步骤再看导入值，在"你看完后的值"里填正确值（同意也照抄），
**只有亲自看完这一行之后**才在"已亲自核对（填 是）"填"是"。填法写在表里的"说明"页。

填好后运行：

```text
python -I -X utf8 data-engineering/scripts/review_table_accuracy.py <填好的 sample.xlsx> --out data-engineering/docs/review-table-20261024/accuracy.md
```

它只统计标"是"的行，逐字段给出核对行数、一致数和准确率，另列未核对的行数、标了"是"却没填值的行数和每一处不一致；
行必须正是 `sample.json` 的那些。把 `accuracy.md`、`accuracy.json` 连同填好的表一起提交，即为公开的抽样准确率。

## 接受是 owner 的决定

看过公开的准确率后，是否接受由 owner 决定。接受时运行：

```text
uv run --project backend python -m app.data.recipe_tags --accept-batch recipe-tags-v1/review-table-20261024
```

它只把这一批 `llm` 条目设为 `reviewed: true`，不动冻结的 `recipe-tags-v1/llm` 批次。接受后有 91 道菜
三个关键字段都已决定，规划器开始读它们；另外 17 道还有冻结模型批次的字段，仍不进入结构化规划。
重跑标签命令时，值没变的条目保持 `reviewed`。

另：导入角色为 sauce 或 dessert 的菜里，有 9 道的蛋白来源是规则给的 egg、soy 或 legume
（规则在角色未定时算出）。规则优先，导入不改它们；它们不填正餐，不影响蛋白不重复的检查。

## 复现

离线，用装有 openpyxl 的 Python，在仓库根目录：

```text
python -I -X utf8 data-engineering/scripts/import_review_table.py <review.xlsx> --base 5238449433d381af8a8304bb14d37713087b902a
cd backend && uv run python -m app.data.recipe_tags
```

第一步只写本目录；第二步只用规则（不带 `--llm`），不调用模型。
