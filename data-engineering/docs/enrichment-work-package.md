# 数据富化工作包（交给 dataset 组员的 agent 执行）

v1 release 已经冻结：8,718 道菜谱 / 443 个规范食材，来自 1,642,647 条上游记录。
这个工作包把它补齐到能支撑规划、安全过滤和 held-out 出题的程度。

依据 `decisions/ADR-0024`（私有知识库）：**复核不再是发布门槛。** 你做完即算完成，
人工事后抽查；抽查发现问题按新版本修正，不回头堵住流程。

---

## 0. 先量一遍，别信这份文档

这些数字是 2026-09-16 量的，你动手前自己重跑一次确认：

```bash
python - <<'PY'
import json, collections
ings=[json.loads(l) for l in open("data/release/v1/ingredients.jsonl",encoding="utf-8")]
rs=[json.loads(l) for l in open("data/release/v1/recipes.jsonl",encoding="utf-8")]
print("ingredients:",len(ings),"recipes:",len(rs))
print("有 fdc_id 的食材:",sum(1 for i in ings if i["fdc_id"]))
print("有 dietary_tags 的菜谱:",sum(1 for r in rs if r["dietary_tags"]))
print("有 prep/cook 的菜谱:",sum(1 for r in rs if r["prep_minutes"] or r["cook_minutes"]))
print("food_group:",collections.Counter(i["food_group"] for i in ings).most_common())
PY
```

预期：`fdc_id` 0 个、`dietary_tags` 0 条、时长 0 条、16 种 food_group。

---

## 1. 四件事，按这个顺序做

### 任务 A — 饮食标签（最容易，先做完建立信心）

**不需要任何新数据。** 443 种食材全部已有 `food_group`，其中 299 种靠它就能定
（vegetable / fruit / dairy / grain / plant_milk / herb / seasoning / sweetener /
leavening / liquid / beverage / grain）。

需要你判断的是剩下 **144 种**：`protein` 60、`condiment` 40、`flavoring` 19、
`prepared` 17、`fat` 8。判断内容只有一件事：**动物来源还是植物来源。**

绝大多数一眼可定（beef、chicken、lentil、cashew、anchovy、black beans），难的是
`condiment` 和 `prepared`（鱼露、蚝油、伍斯特酱、明胶、某些人造黄油）。难的那些要
查，并把依据记下来。

判完之后，这四个标签**确定性推导**，不要用模型猜：

| 标签 | 推导规则 |
|---|---|
| `dairy-free` | 无 `dairy` food_group 的食材，且无 `milk` 过敏原 |
| `gluten-free` | 无 `gluten` 过敏原。`gluten_candidate` 视为**不满足**（保守） |
| `vegetarian` | 无动物来源食材，但允许 dairy / eggs / honey |
| `vegan` | 无动物来源食材，且无 dairy、eggs、honey |

蕴含闭包已有现成的表，别再造一套：`data/recipes/dietary-tag-implications.json`
（仓库根目录下，不是 data-engineering 里）。

### 任务 B — 营养（这是硬骨头）

443 种食材的 `fdc_id` 和 `foodon_id` **全部为 null**。没有它就算不出营养。

**做法**：对每一种食材，从本地版本化的 USDA FoodData Central 下载里检索候选，选一个，
然后**必须记录四样东西**：

```json
"nutrition_mapping": {
  "fdc_id": 173410,
  "chosen_name": "Butter, salted",
  "confidence": 0.91,
  "evidence": "为什么是它——同义词、food_group 一致、排除了 whipped / unsalted 变体",
  "rejected": [
    {"fdc_id": 173430, "name": "Butter, whipped", "why": "体积密度不同，会让按克换算偏高"}
  ]
}
```

**这四样不是文档要求，是 `ADR-0024` 第 1 节的硬性条件。** 不记录证据的映射等于
「第一个搜索结果自动成为事实」，那是 `ADR-0012` 从一开始就禁止的，`ADR-0024` 没有放宽它。
放宽的只是"必须由人来做这个推理"。

**批量用本地版本化下载，不要打 USDA API**（配额和不稳定性）。API 只用于个别核查。

置信度低、或候选之间差异会显著改变营养的，**保持 `unresolved`**。不要用零，不要猜，
不要拿相近食材顶替。`unknown` 在下游是有明确语义的，零不是。

映射完之后算每道菜谱的营养：食材量 → 质量换算 → 累加 → 按份数除。跨维度换算
（体积→质量）需要密度，没有密度的保持 `unknown`，不要用水的密度代替。

**份量是估计值的那 2,644 条**（`servings_basis == "range_lower_bound"`），算出来的
每份营养要继承这个不确定性——在输出里标出来，别让下游以为它和原文声明的一样可靠。

### 任务 C — 烹饪时长（上游数据里根本没有）

8,718 条里 0 条有 `prep_minutes` / `cook_minutes`。RecipeNLG 原始数据就不带。

**做法**：从 `instructions` 文本里抽取显式时长（"bake for 30 minutes"、"simmer 10 min"），
按步骤累加。抽不到显式时长的，按烹饪方法和食材数估算。

**必须记录依据**，照搬 release 里已有的 `servings_basis` 那个模式：

```json
"prep_minutes": 15,
"cook_minutes": 30,
"time_basis": "stated_in_instructions" | "estimated_from_method" | "unknown"
```

`estimated_from_method` 和 `stated_in_instructions` 在下游不是一回事——时长约束题
只能用前者中的后一种。**不要把两者混成一个数字。**

### 任务 D — 餐次亲和度（注意：不是硬标签）

**不要输出 `meal_types: ["breakfast"]` 这种硬分类。** 燕麦粥更适合早餐是约定俗成，
不是规则；一个因为标签不符就拒绝排布的规划器不是更聪明，是更笨。

**做法**：输出每个餐次的亲和分数，例如：

```json
"meal_affinity": {"breakfast": 0.9, "lunch": 0.3, "dinner": 0.15, "basis": "..."}
```

规划器把它当**软偏好**用，不当过滤器（`ADR-0024` 第 5 节）。它要避免的是约定俗成
本来在防的那些结果——同一道重菜一周三次、早餐和晚餐分不出区别——靠偏好和多样性，
不靠禁止。

---

## 2. 红线（这几条没有例外）

### 🔴 不要碰 `data/recipes/recipes.json`

这是仓库根目录下那个 30 道菜的运行时目录。它同时是：

- `backend/app/evaluation/workbench.py`、`v2_packets.py`、`heldout_set.py` 的默认输入
- `scripts/check_heldout_episodes.py` 和 `report_catalog_reality.py` 的校验基准
- `backend/app/core/paths.py` 定位仓库根目录的标记文件

**原地扩容会改变所有已经报告过的 v1 评价数字的计算条件**，那违反 `ADR-0020` 第 3 节。
这个坑已经踩过一次：给商品加包装规格改掉了一份已提交的评价报告，最后是另开
`fairprice-products-v2.json` 解决的。

**照同样的办法**：输出写到 `data/recipes/recipes-v2.json` 和
`data/ingredients/ingredients-v2.json`，`recipes.json` 保持不动。

### 🔴 不要碰过敏原

`ADR-0024` 第 3 节明确把过敏原排除在 agent 推断之外，只能由确定性规则从规范食材集推导
——也就是 v1 release 现在这个做法。

原因：营养算错 15% 是可恢复、用户看得见的；过敏原标错两样都不是，它是一条安全声明，
后果落在用户身上。任务 A 里你判定动植物来源，**不等于**你可以重标过敏原。

食材的过敏原状态是 `unknown` 时，被过敏原约束**排除**，不是被放行。

### 🔴 不要提交这些

- RecipeNLG 原始数据（许可限研究/教育非商业，必须由下载者本人接受条款）
- 任何 API key、token、`.env`
- USDA / FoodOn 的整库转载（只提交你用到的版本化 manifest 和校验和）

### 🔴 不要原地改 v1

v1 是冻结快照。所有产出进 `data/release/v2/`，带自己的 `release_manifest.json`、
`quality_report.md` 和 digest。

---

## 3. 验收

做完之后这些必须成立：

1. `data/release/v2/` 存在，manifest 里 `known_gaps` 如实列出仍然缺的东西
   （**不要写空数组来显得干净**，v1 的 manifest 就是个好样板）
2. 每一条 `nutrition_mapping` 都有 `evidence` 和 `rejected`；抽 20 条人工看过去，
   理由要站得住
3. `unresolved` / `unknown` 的数量**明确报出来**，带分母。覆盖率不到 100% 是正常的，
   假装到了才是问题
4. 运行时目录跑得起来：
   ```bash
   docker compose run --rm backend uv run --no-sync python -m app.data.import_catalog --recipes data/recipes/recipes-v2.json
   ```
5. `python scripts/check_heldout_episodes.py` 仍然 `No problems found.`
   （现有 3 条题不能被你的改动搞坏）
6. `python scripts/report_catalog_reality.py` 重新生成，新的目录现状页出来

## 4. 交回来时 PR 里要写

1. 四个任务各自的覆盖率，**带分母**
2. `unresolved` 的分布——哪一类食材最难映射
3. 抽查了哪 20 条，结论是什么
4. **已知的错误**（这一项不准留空；一个声称零错误的富化管线只说明没认真找）
5. 对下游的影响：规划器、评价、出题分别受什么影响
6. 会不会产生网络请求或 API 调用

## 5. 需要人拍板的，别自己定

- 营养映射的置信度接受阈值（这是评价参数，按 `ADR-0020` 冻结前不能随便调）
- 密度换算表用哪个来源
- 餐次亲和度接入规划器的权重

其余工程决定你自己做，PR 里写清理由即可。
