# data release v3 第 2 波新增菜谱的 60 道人工抽检（issue #392 补充）

抽检对象只是 data release v3 第 2 波（第一次 v3 构建之后加的那一波，`v3_selected.csv` 里 wave 2）发布出来的菜谱
（`review_sampling.new_recipes(wave=2)`，5,263 道）。第一次 v3 构建新增的 3,927 道已经在 `../manual-check-20261103/` 抽检，
那一轮的文件不动。三项检查和口径与那一轮相同：菜谱完整、步骤合理、份量正常，三项全对算正确。"至少 95%"按点估计读，
同时报告 Wilson 95% 区间。

第 2 波由 OpenAI API（`gpt-5.4-mini`）和 Claude 子代理（`claude-sonnet-5-5`，同一套说明和校验）分别富化了一部分，
菜谱的 `enrichment.by` 写着是哪一个。这一轮不按富化来源分层。

v3 里另有 177 道新增菜谱不在这一轮和第 1 波的抽样范围里：173 道超配额 v2.1 菜谱和 4 道第 1 波菜谱，第一次构建时被
美国菜 20% 上限挡下，这次总数变大后上限不再卡住它们。合并估计的"覆盖"只算两波的菜谱数。

## 文件

- `sample.json`：抽样记录。固定种子 20261104，从第 2 波菜谱里按类别分层抽 60 道（每类至少 3 道，其余按类别大小分）。
- `check.xlsx`：发给复核人的空表，黄色几栏（三项判断、问题说明、已亲自核对）什么都没有预填。
- `check-filled.xlsx`：复核人交回的表。
- `report.md`、`report.json`：由评分脚本生成的复核结果；传入第 1 波表时也包含两波合并估计。不要手改。

`sample.json` 和 `check.xlsx` 由 `python -I -X utf8 data-engineering/scripts/manual_check.py draw --wave 2` 生成（仓库根目录，
离线，需要 openpyxl）。复核人交回后，把表存为 `check-filled.xlsx`，用
`python -I -X utf8 data-engineering/scripts/manual_check.py score --wave 2 data-engineering/docs/manual-check-20261104/check-filled.xlsx`
生成 `report.md` 和 `report.json`，不要手改。第 1 波的表也交回后，加上
`--with data-engineering/docs/manual-check-20261103/check-filled.xlsx`，报告会多一节"Both waves"：每一波是一层，
各带 Wilson 区间，再按两波的菜谱数加权给出合并的正确率（点估计）。第 1 波交回的表只读不改。
测试 `data-engineering/tests/test_review_draws_v3.py` 检查提交的样本就是重新抽出的样本。
