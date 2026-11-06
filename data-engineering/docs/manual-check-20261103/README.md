# data release v3 新增菜谱的 100 道人工抽检（issue #392）

抽检对象只是 data release v3 里新增、v2.2 没有的菜谱（`review_sampling.new_recipes()`）。v2.2 的 8,968 道原样复制，已经在
`../manual-check-20261025/` 抽检过，这里不再抽。三项检查和口径与 2026-10-25 那一轮相同：菜谱完整、步骤合理、份量正常，
三项全对算正确。"至少 95%"按点估计读，同时报告 Wilson 95% 区间。

## 文件

- `sample.json`：抽样记录。固定种子 20261103，从 v3 新增菜谱里按类别分层抽 100 道（每类至少 3 道，其余按类别大小分）。
- `check.xlsx`：发给复核人的空白模板。
- `check-filled.xlsx`：AI 辅助初筛后的复核表。AI 先填三项初步判断并起草问题说明；真人逐道核对来源菜谱，确认或修正最终判断和说明，并在“已亲自核对”栏确认。只有真人确认的行进入评分；AI 不作为独立复核人。
- `report.md`、`report.json`：由评分脚本生成的复核结果，不要手改。

`sample.json` 和 `check.xlsx` 由 `python -I -X utf8 data-engineering/scripts/manual_check.py draw --new` 生成（仓库根目录，
离线，需要 openpyxl）。复核人交回后，把表存为 `check-filled.xlsx`，用
`python -I -X utf8 data-engineering/scripts/manual_check.py score --new data-engineering/docs/manual-check-20261103/check-filled.xlsx`
生成 `report.md` 和 `report.json`，不要手改。测试 `data-engineering/tests/test_review_draws_v3.py` 检查提交的样本就是重新抽出的样本。

报告另列把“看不出”、未核对和待补填都计作未确认正确的全样本比例；这只是保守样本产出比例，不是准确率估计。
本轮对菜谱完整性的判定比 2026-10-25 的 v2.2 复核更严格，缺水、盐、抹锅油或配餐等步骤用料也会记为缺项；两轮结果不能直接比较。

## 2026-11-06 修复后的变化（issue #426）

本轮抽检之后，下列样本菜被 issue #426 的修复改动（`data-engineering/docs/v3-repair-20261106/`）。复核结论针对改动前的版本，未重新复核：

- `RCP2_175BE2BD8D3F` Alfredo Pasta：份数 2 改为 3（复核判份量不正常；步骤写 "Serves 2 to 3"），`sample.json` 的 servings 随之重抽为 3，复核表和报告保持原样。
- `RCP2_8993605D4EA0`、`RCP2_B719A66E8B47`：配餐的蒸米饭改按熟米饭计营养（`cooked_rice`，克重不变）。
