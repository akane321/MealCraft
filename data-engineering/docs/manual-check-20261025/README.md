# release v2.2 的 100 道人工抽检（03 方案 2.7，owner 2026-10-25）

复核人 liu-ub 逐道检查 100 道 release 菜谱的三项：菜谱完整、步骤合理、份量正常。目标是三项全对的比例不低于 95%。

## 文件

- `sample.json`：抽样记录。固定种子 20261025，从 release v2.2 按类别分层抽 100 道（每类至少 3 道，其余按类别大小分）。
- `check.xlsx`：发给复核人的空表，什么都没有预填。
- `check-filled.xlsx`：复核人交回的表。
- `report.md`、`report.json`：由下面的命令生成，不要手改。

`sample.json` 和 `check.xlsx` 由 `python -I -X utf8 data-engineering/scripts/manual_check.py draw` 生成，
报告由 `python -I -X utf8 data-engineering/scripts/manual_check.py score data-engineering/docs/manual-check-20261025/check-filled.xlsx`
生成（仓库根目录，离线，需要 openpyxl）。测试 `backend/tests/test_release_reviews.py` 检查提交的样本就是从 release 重新抽出的样本。

## 口径

- 只有"已亲自核对"填了"是"的行才计入。
- 三项都是"对"算正确；任何一项"错"就算错误，即使别的项"看不出"；没有"错"但有"看不出"的，单列，不计入正确率。
- 每个"错"记在它那一项下面，一道菜可以同时记在两项下。
- 正确率附 Wilson 95% 置信区间。

## 复核方式

复核人用 AI 辅助审阅（AI 先读食材和步骤、写出意见），2026-10-26 在项目聊天里确认"AI 辅助，本人逐道确认"。
交回的表里附有 AI 辅助审阅过程的记录页（"最终确认记录"、"最终审核说明"、"原问题说明归档"），按原样保留。
