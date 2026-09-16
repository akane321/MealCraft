# 数据库组员操作流程

## 第一次理解工程

1. 阅读 `README.md`、`docs/data-dictionary.md` 和 `docs/cleaning-decisions.md`。
2. 运行 `scripts/run_demo.ps1`。
3. 先看 `reports/latest.md`，再抽查 `data/curated/recipes.jsonl`。
4. 打开三个候选/复核文件：
   - `ingredient_review_queue.csv`
   - `foodon_mapping_candidates.csv`
   - `usda_foundation_candidates.csv`
5. 找出至少三个“rank 1 仍然错误”的例子，理解候选生成与事实确认的区别。

## 添加真实 RecipeNLG 数据

1. 本人进入 RecipeNLG 官方页面，阅读并接受研究/教学使用条款。
2. 把 `full_dataset.csv` 放入 `data/raw/recipenlg/`。
3. 不修改原文件，不提交 Git。
4. 使用固定 `--seed 5105` 抽取 5,000 条 `Gathered` 记录。
5. 保存 `reports/run_manifest.json` 中的输入哈希、抽样参数和转换版本。

## 改进归一化规则

正确流程：

1. 在复核表中记录决定和理由。
2. 如果是通用别名：编辑 `scripts/build_ingredient_aliases.py` 里的 `TABLE`（分组、带注释、
   有重复别名检查），然后 `python scripts/build_ingredient_aliases.py` 重新生成
   `config/ingredient_aliases.csv`。也可直接手工补 CSV。
3. 如果是通用单位，加入 `config/units.csv`。
4. 如果是处理方式或描述词，加入 `config/preparation_terms.txt`。有辨识意义的词
   （green onion / red pepper 之类）不要当描述词。
5. 为新规则增加测试。
6. 重新运行完整管道，比较修改前后的覆盖率与错误样本。

不要直接编辑 `data/curated/*.jsonl`。这些是可再生输出，直接修改会使来源和结果无法复现。

## 建议的第一轮分工结果

- 原始池：5,000 条固定抽样 RecipeNLG 食谱；
- 人工抽查：200 条食材行，并记录通过和失败；
- 标准食材：先覆盖高频 200–300 个内部 ID；
- USDA/FoodOn：只提交已人工确认的映射；
- 报告：记录数量、单位、别名、NER 对齐和映射覆盖率；
- 冻结版本：给规划器和 Evaluation 使用相同的版本号和内容哈希。

## 提交前检查

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m unittest discover -s tests -v
python -m mealcraft_data.cli validate `
  --recipes data/curated/recipes.jsonl `
  --ingredients data/curated/ingredients.jsonl
git diff --check
git status
```

确认原始 RecipeNLG、API key、下载缓存和带个人路径的运行文件没有进入 Git。

