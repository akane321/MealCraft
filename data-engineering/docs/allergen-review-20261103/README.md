# data release v3 新增菜谱的过敏原复核（issue #392）

复核对象只是 data release v3 里新增、v2.2 没有的菜谱（`review_sampling.new_recipes()`）。v2.2 的菜谱原样复制，已经在
`../allergen-review-20261025/` 复核过。分层和口径与 2026-10-25 那一轮相同：每道菜归到它目录里最少见的那种过敏原，没有过敏原的
单独一层，每层至少 3 道，其余按层的大小分；总体一致率按各层在新增菜谱里的占比加权。"至少 95%"按点估计读，同时报告 Wilson 95% 区间。

和上一轮的两处不同：

- 这一轮没有 AI 候选（没有 `ai_candidates.json`），表里"AI 候选"和"AI 说明"两栏是空的，报告也不算 AI 一致率。
- 说明页按目录的实际做法写"A 或 B"：目录只取第一项的过敏原（上一轮说明页写成"两样都算"，和目录不符）。

## 文件

- `sample.json`：抽样记录。固定种子 20261103，从 v3 新增菜谱里抽 50 道。
- `review.xlsx`：发给复核人的空白模板。
- `review-filled.xlsx`：AI 辅助起草问题备注后的复核表；本轮没有 AI 过敏原候选。真人逐道查看食材和步骤、填写确认的过敏原并标记亲自核对。只有真人确认行计入评分；AI 不作为独立复核人。
- `report.md`、`report.json`：由评分脚本生成的复核结果，不要手改。

`sample.json` 和 `review.xlsx` 由 `python -I -X utf8 data-engineering/scripts/allergen_review.py draw --new` 生成（仓库根目录，
离线，需要 openpyxl）。复核人交回后，把表存为 `review-filled.xlsx`，用
`python -I -X utf8 data-engineering/scripts/allergen_review.py score --new data-engineering/docs/allergen-review-20261103/review-filled.xlsx`
生成 `report.md` 和 `report.json`，不要手改。测试 `data-engineering/tests/test_review_draws_v3.py` 检查提交的样本就是重新抽出的样本。

## 2026-11-06 修复后的变化（issue #426）

本轮抽检之后，下列样本菜被 issue #426 的修复改动（`data-engineering/docs/v3-repair-20261106/`）。复核结论针对改动前的版本，未重新复核：

- `RCP2_703781931A43`：罐装椰奶改按罐上写的 14 oz 称重（`package_mass`）。
- `RCP2_DB51910E060D`：撤出计划（步骤用黄油涂模、清单没有黄油，却标了 dairy-free）。
