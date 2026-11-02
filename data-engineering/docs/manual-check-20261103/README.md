# data release v3 新增菜谱的 100 道人工抽检（issue #392）

抽检对象只是 data release v3 里新增、v2.2 没有的菜谱（`review_sampling.new_recipes()`）。v2.2 的 8,968 道原样复制，已经在
`../manual-check-20261025/` 抽检过，这里不再抽。三项检查和口径与 2026-10-25 那一轮相同：菜谱完整、步骤合理、份量正常，
三项全对算正确。"至少 95%"按点估计读，同时报告 Wilson 95% 区间。

## 文件

- `sample.json`：抽样记录。固定种子 20261103，从 v3 新增菜谱里按类别分层抽 100 道（每类至少 3 道，其余按类别大小分）。
- `check.xlsx`：发给复核人的空表，黄色几栏（三项判断、问题说明、已亲自核对）什么都没有预填。

`sample.json` 和 `check.xlsx` 由 `python -I -X utf8 data-engineering/scripts/manual_check.py draw --new` 生成（仓库根目录，
离线，需要 openpyxl）。复核人交回后，把表存为 `check-filled.xlsx`，用
`python -I -X utf8 data-engineering/scripts/manual_check.py score --new data-engineering/docs/manual-check-20261103/check-filled.xlsx`
生成 `report.md` 和 `report.json`，不要手改。测试 `data-engineering/tests/test_review_draws_v3.py` 检查提交的样本就是重新抽出的样本。
