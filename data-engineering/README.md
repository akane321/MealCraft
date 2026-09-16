# MealCraft Data Cleaning Demonstration

本目录演示如何把大型但不完整的 RecipeNLG 原始食谱，转换成 MealCraft 可使用、可审计、可继续补充营养和超市商品信息的数据层。

核心原则：

1. 原始数据只读，清洗结果写入新的分层目录。
2. 原始值、解析值和人工修正值分开保存。
3. 缺失信息保持 `null`，不使用大模型捏造营养、份量或过敏原事实。
4. 每条记录保留来源、许可、处理版本、置信度和复核状态。
5. 食材库、食谱库、营养参考库和 FairPrice 商品库使用独立 ID，通过映射表连接。

## 目录

```text
DataCleaning/
├── config/                    # 可审查的单位、别名、过敏原规则
├── data/
│   ├── fixtures/              # 可公开的 synthetic 脏数据
│   ├── raw/                   # 本地原始数据，不提交 Git
│   ├── staging/               # 解析后的中间结果
│   ├── curated/               # 可被 MealCraft 导入的数据
│   ├── review/                # 人工复核队列
│   └── reference/             # USDA/FoodOn 等参考源
├── schemas/                   # JSON Schema 数据契约
├── src/mealcraft_data/        # 清洗实现
├── tests/                     # 单元测试
└── reports/                   # 质量报告和运行清单
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
