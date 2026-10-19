# MealCraft Data Engineering

本目录把大型但不完整的 RecipeNLG 原始食谱，转换成 MealCraft 可使用、可审计、可继续补充营养和
超市商品信息的数据层，并切出版本化 release。Release 目前**尚未导入**运行时目录
（`data/recipes/recipes.json`）；导入进度见 `docs/current-status.md`。

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

## 菜谱与食材标签 v1 的抽检（Reviewing recipe and ingredient tags）

```bash
uv run --project backend python -m app.data.recipe_tags          # 只用规则；之前模型给的答案保留并复用
uv run --project backend python -m app.data.recipe_tags --llm    # 规则定不了的再问模型，默认花费上限约 US$5
```

规则在 `backend/app/data/recipe_tags.py`，产出 `data/recipes/recipe-tags-v1.json` 和
`data/ingredients/ingredient-tags-v1.json`，导入器（版本 6）按 release < 标签文件 < 运行时写入的顺序
写进数据库。覆盖率和模型花费见 `docs/recipe-tags-v1-report.md`。`--reask` 丢掉之前模型的答案重新问。
运行时写入的菜谱标签会在重新导入时保留，前提是写入方把它标出来：删掉该字段在 `estimated` 里的条目（人定的值不是估计），
或把条目的 `reviewed` 设为 `true`。

抽检包是 `docs/recipe-tags-v1-sample.json`（种子固定）：按正餐角色和判定方式（rule、llm、未定）分层抽了
100 多道菜，另有全部"易坏"食材、全部基础调料和一些随机食材。owner 的做法：

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
