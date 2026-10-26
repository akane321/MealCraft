# release v2.2 的过敏原复核（03 方案 2.5，owner 2026-10-25）

复核人 liu-ub 逐道确认 50 道 release 菜谱的过敏原，和目录现有的过敏原对比。

## 文件

- `sample.json`：抽样记录。固定种子 20261025，从 release v2.2 抽 50 道，按过敏原种类分层：每道菜归到它目录里最少见的那种过敏原，
  没有过敏原的单独一层；每层至少 3 道，其余按层的大小分。少见的过敏原因此被多抽，总体一致率按各层在 release 里的占比加权。
- `ai_candidates.json`：Claude 只读食材原文和步骤给出的候选过敏原（AI，2026-10-25），和目录不同时写了理由。复核表里和目录并排显示，只是参考。
- `review.xlsx`：发给复核人的表。"你确认的过敏原"和"已亲自核对"两栏是空的。
- `review-filled.xlsx`：复核人交回的表。
- `report.md`、`report.json`：由下面的命令生成，不要手改。

`sample.json` 和 `review.xlsx` 由 `python -I -X utf8 data-engineering/scripts/allergen_review.py draw` 生成，
报告由 `python -I -X utf8 data-engineering/scripts/allergen_review.py score data-engineering/docs/allergen-review-20261025/review-filled.xlsx`
生成（仓库根目录，离线，需要 openpyxl）。

## 口径

- 只有"已亲自核对"填了"是"的行才计入；填 null（看不出）的单列；代码写错的列为"请重填"。
- 复核人确认的过敏原集合和目录完全相同才算一致。不同之处分两类：目录漏标（复核人有、目录没有）和目录多标（目录有、复核人没有），按过敏原分别计数。
- 与目录相同的口径：配菜建议和可选配料不算；"A 或 B"两样都可能用，两样的过敏原都算。
- 因为 AI 候选当时就显示在复核人面前，"AI 候选和复核人一致"的比例不是 AI 的独立准确率。
