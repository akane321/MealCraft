# 冻结模型批次的复核批次 `recipe-tags-v1/review-table-20261024`（owner 2026-10-24）

复核人 liu-ub 为冻结的模型批次（`recipe-tags-v1/llm`，422 道菜）填了一份逐字段复核表。表里的决定是
AI 预填、在聊天里按"菜品类型"确认的，没有人逐行看过食材和步骤："已亲自核对（填 是）"一栏每一行都是空的。
所以这些值**不是人工复核**。owner 2026-10-24 选定 ADR-0076 的路线：

1. 只把现行规则留空的字段导入为一个 AI 估计批次，标为 `llm`、`reviewed: false`；
2. 现行规则已经给出的字段，以规则为准，不用表里的值；
3. 表里不在复核人可选角色范围内的值保持待定，不为此改规则；
4. 冻结字段里现行规则已经能定的，也并入本批（owner 2026-10-24 另一项决定），写规则值，同样等待接受；
5. 复核人亲自核对一份固定种子的抽样（两部分都抽），公开分层的抽样准确率；
6. 之后由 owner 决定是否接受这一批（`--accept-batch`）。在那之前规划器不读本批的任何值。

## 文件

- `decisions.json`：复核表的导入结果。`provenance` 记来源，`counts` 记数字，`accepted` 是导入的值（按菜），
  `skipped` 是每一个没导入的表格值及原因。由 `data-engineering/scripts/import_review_table.py` 生成，不要手改。
  它是表导入值的唯一来源：一个值从这里去掉，重新生成后那个字段就回到未标注。
- `sample.json`：抽样记录（种子、每道菜属于哪一层、哪个子层和角色格、要核对的值）。
- `sample.xlsx`：给复核人亲自核对用的表（见下文"抽样核对"）。
- 核对后由 `review_table_accuracy.py` 生成的 `accuracy.md` 和 `accuracy.json`（尚未生成）。

## 来源

| 项目 | 值 |
| --- | --- |
| 复核表 | liu-ub 的复核表（未提交进仓库），SHA-256 `ff85917c2821dc75c6f5e1f100191df4836309298574357fd246ad9327ed2095` |
| 读取的工作表 | `1 可用池277道`、`2 其余145道`（每行是一道菜的一个字段） |
| 行数 / 菜数 | 815 行 / 422 道，全部在复核包里 |
| 已亲自核对 | 0 行（该栏每一行都是空的） |
| 复核包 | `data-engineering/docs/role-rules-20261023b/review.json`，SHA-256 `d7dcb750eb57802419ce519816a8f8e813ca03d30d57432cfb4f11348f2248de` |
| 基准提交 | main 的 `5238449`（完整提交号记在 `decisions.json` 的 `provenance.base_commit`） |

每行的取值按"你的决定"解读：同意 Claude 建议取建议值（去掉开头的"被规则挡住 →"），同意模型原值取模型值，
其他情况取"其他值"；聊天确认或被规则挡住而没有其他值的，取建议值；没有决定或"跳过"的不取值。
`staple（主食）`、`pork（猪）,beef（牛）`、`true（是）`、`null（未知/不放行）` 这类写法去掉括号里的注释，
多个值按 `,`、`，` 或 `、` 分开。

## 本批的两部分

| 部分 | 值 | 菜 | method | 说明 |
| --- | ---: | ---: | --- | --- |
| 复核表导入值 | 214（角色 106、主食 106、蛋白来源 2） | 108 | `llm` | AI 预填，只在规则留空的字段 |
| 规则已定的冻结字段 | 562（角色 214、主食 214、蛋白来源 134） | 269 | `rule` | 冻结的模型值换成现行规则的值 |

两部分都是 `batch = "recipe-tags-v1/review-table-20261024"`、`reviewed = false`；44 道菜两部分都有。
规则部分的蛋白来源里，有一部分是规则自己的不变量：最终角色是甜品、饮料、酱料或自制主食时没有主要蛋白（`[]`），
这个 `[]` 标 `rule`，角色还在等复核或属于本批时跟着本批走，否则是普通规则值。
规则部分里，163 道菜的规则值全部等于冻结的模型原值，106 道至少有一项不同。

`python -m app.data.recipe_tags` 构建时的优先级：owner 逐道决定 > 现行规则 > 复核表 > 冻结的模型值。
冻结字段（`recipe-tags-v1/llm` 的未复核值，重跑时也包括本批自己的未复核值）若现行规则能定，就写规则值进本批；
若规则留空，复核表有值且在当前 `review_roles` 里就用表值，否则保持冻结的模型值。本批里表导入的旧值不会被冻结带下去，
只由 `decisions.json` 重新写入。最后按最终角色执行一次上面的不变量。接受前后连续重新生成，结果逐字节相同。

## 规划器的门禁

`app.data.tag_files.waits_for_review` 是唯一的定义：`llm` 且未复核，或 `batch == recipe-tags-v1/review-table-20261024`
且未复核（不论 method）。`meal_composition.unreviewed`（以及经由它的 `meal_role_of`、`catalog_role_admits`、
`product_path.recipe_tags`、换菜时的角色判断）都用它；其他 batch 的规则值不受影响。

当前有 417 道菜的关键字段在等复核。接受本批后放行 326 道；仍有 91 道被挡，因为它们还有冻结模型批次
（`recipe-tags-v1/llm`）的字段，规则和复核表都没给值（共 135 个字段）。

## 复核表的导入数字

| 字段 | 导入 | 规则已定且一致 | 规则已定但不同 | owner 逐道决定 | 超出可选角色 | 表里为 null |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `meal_role` | 106 | 172 | 42 | 5 | 16 | 28 |
| `contains_staple` | 106 | 180 | 34 | 5 | 16 | 28 |
| `protein_sources` | 2 | 18 | 7 | 0 | 0 | 50 |

原因码合计：`rule_decided_agrees` 370、`rule_decided_conflicts` 83、`owner_decided` 10、
`outside_allowed_roles` 32、`left_open` 106、`skipped_by_reviewer` 0、`staple_inconsistent` 0、`invalid_value` 0。
`contains_staple` 由导入的角色推出（`one_bowl`、`staple` 为 true，其他为 false）再和表里的值核对，不一致就两项都不导入；
角色没导入，它也不导入，"超出可选角色"和"表里为 null"跟随它的角色。

导入的角色：staple 24、snack 24、sauce 24、dessert 20、soup 10、vegetable 2、breakfast 1、one_bowl 1。
导入的蛋白来源只有两道：Vietnamese Pâté Chaud（`pork`）和 Ramen Hot And Sour Soup（`egg`，原模型值为
pork、beef、shellfish、egg；食材里的肉是可选的未指明肉类）。

## owner 2026-10-24 的逐道决定

六处聊天确认与现行规则冲突，owner 在聊天中逐条决定。五道写进 `backend/app/data/recipe_tags.py` 的 `OWNER_ROLES`：

| 菜 | 聊天确认 | 规则 | owner 决定 |
| --- | --- | --- | --- |
| Asian Wraps（`RCP2_A84B4E56257C`） | snack | protein_main | 例外：snack |
| Potato Croquettes With Parmesan（`RCP2_E5862A12458B`） | snack | staple | 例外：snack |
| Thai Sweet Potato Stew（`RCP2_66540AABF0E0`） | soup | staple | 按规则：staple |
| Sweet Potato & Pea Curry（`RCP2_F480AAE0C111`） | vegetable | staple | 按规则：staple |
| Pupusas（`RCP2_3C310D373BB9`） | one_bowl | staple | 按规则：staple |
| Recipe Of 1985'S Burleson County Kolache（`RCP2_24D1FD24F7F1`） | sauce | 留空；sauce 不在烘焙品的可选角色里 | 保持待定（不导入，仍冻结） |

`OWNER_ROLES` 里的角色和 `contains_staple`（staple 为 true，snack 为 false）记为人的决定而不是 AI 估计：
`method = "rule"`、`batch = "recipe-tags-v1/owner-20261024"`、`reviewed = true`，立即生效，冻结值和本批都不能盖过它。
`protein_sources` 不变，仍按规则；这五道的蛋白来源都是普通规则值，所以五道现在都不被门禁挡，规划器照常读。
另一道 Pupusas (El Salvadorean Tortilla)（`RCP2_BBD46E78E711`）不在 owner 点名的范围里，按规则（staple）进本批，等待接受。

## 抽样核对

`sample.json` 和 `sample.xlsx` 共 46 道菜、92 行，种子 `20261024`：

- **表导入层**（31 道）：第一轮的 30 道不变（按导入的角色分层，每层至少 1 道，其余按层的大小分配：
  staple 6、snack 6、sauce 6、dessert 5、soup 3、breakfast 1、one_bowl 1、vegetable 1、只导入蛋白来源 1），
  另把"只导入蛋白来源"那层剩下的一道也抽进来，这一层两道都看（Pâté Chaud 和 Ramen Hot And Sour Soup）。
- **规则已定层**（15 道）：从 269 道里排除 owner 决定的菜后抽取。先分"规则值等于模型原值"（163 道）和
  "规则值不同于模型原值"（106 道）两个子层，再按本批里的角色分格（规则部分没有角色的记为"只有蛋白来源"），
  每格至少 1 道，其余按大小分配：

  | 子层 | 角色格（菜数 → 抽取） |
  | --- | --- |
  | 等于（抽 8） | staple 61 → 3、one_bowl 36 → 2、protein_main 24 → 1、只有蛋白来源 42 → 2 |
  | 不同（抽 7） | protein_main 37 → 2、vegetable 22 → 1、staple 19 → 1、只有蛋白来源 13 → 1、sauce 10 → 1、one_bowl 5 → 1 |

`sample.xlsx` 每行是一道菜的一个字段，要核对的就是本批里的值（"本批的值"一栏）。表里所有菜混在一起按编号排序、
重新编序号；不显示模型原值，没有"可选角色"一栏，也没有任何一栏标明这一行来自复核表还是规则。复核人填了不在可选范围里的角色，
照常记为不一致。复核人本人逐行核对：先看食材和步骤再看值，在"你看完后的值"里填正确值（同意也照抄），
**只有亲自看完这一行之后**才在"已亲自核对（填 是）"填"是"。填法写在表里的"说明"页。

填好后运行：

```text
python -I -X utf8 data-engineering/scripts/review_table_accuracy.py <填好的 sample.xlsx> --out data-engineering/docs/review-table-20261024/accuracy.md
```

它只统计标"是"的行，按层（表导入层、规则已定层及其两个子层）和合计，再按字段，给出核对行数、一致数和准确率，
另列未核对的行数、标了"是"却没填值的行数，以及**无法识别、请重填**的行（如"是/否"、拼错的代码），这些行既不算一致也不算不一致。
行必须正是 `sample.json` 的那些。把 `accuracy.md`、`accuracy.json` 连同填好的表一起提交，即为公开的抽样准确率。

## 接受是 owner 的决定

看过公开的准确率后，是否接受由 owner 决定。接受时运行：

```text
uv run --project backend python -m app.data.recipe_tags --accept-batch recipe-tags-v1/review-table-20261024
```

它把这一批所有未复核的值（`llm` 和 `rule` 都算）设为 `reviewed: true`，不动冻结的 `recipe-tags-v1/llm` 批次和普通规则值。
接受只改数据：仓库里的测试在接受前后都成立。接受后再跑 `python -m app.data.recipe_tags`：复核表的值保持 `reviewed`
（值没变的话）；规则已定的那部分回到普通规则值（`method rule`、`recipe-tags-v1/rules`），只有跟着本批角色走的不变量 `[]`
仍记在本批、保持 `reviewed`；规划器照常读。

`--reask` 会撤销冻结：规则能定的冻结字段直接放行，不经过本批（见 `data-engineering/README.md`）。

## 开发报告

仅规则重生成之后重跑四份开发报告，差异和原因见本分支的提交说明。

## 复现

离线，用装有 openpyxl 的 Python，在仓库根目录：

```text
python -I -X utf8 data-engineering/scripts/import_review_table.py <review.xlsx> --base 5238449
cd backend && uv run python -m app.data.recipe_tags && cd ..
python -I -X utf8 data-engineering/scripts/import_review_table.py <review.xlsx> --base 5238449
```

第一步写 `decisions.json`（`--base` 解析为完整提交号）；标签文件还没带上表导入值或规则部分时就此停下。
第二步只用规则（不带 `--llm`），不调用模型；第三步按重生成后的标签文件写抽样。
