# data release v3 第 2 波新增菜谱的过敏原复核（issue #392 补充）

复核对象只是 data release v3 第 2 波（第一次 v3 构建之后加的那一波，`v3_selected.csv` 里 wave 2）发布出来的菜谱
（`review_sampling.new_recipes(wave=2)`，5,263 道）。第一次 v3 构建新增的菜谱已经在 `../allergen-review-20261103/` 抽了，
那一轮的文件不动。分层和口径与那一轮相同：每道菜归到它目录里最少见的那种过敏原，没有过敏原的单独一层，其余按层的大小分；
一波内的一致率按各层在这一波里的占比加权。"至少 95%"按点估计读，同时报告 Wilson 95% 区间。

和第 1 波的不同：

- 这一轮抽 30 道。第 2 波有 13 层，每层至少 3 道放不下，所以每层至少 2 道，其余 4 道按层的大小分。
- 和第 1 波一样没有 AI 候选（没有 `ai_candidates.json`），表里"AI 候选"和"AI 说明"两栏是空的；说明页同样写明
  "A 或 B"目录只取第一项的过敏原。

v3 里另有 177 道新增菜谱不在这一轮和第 1 波的抽样范围里：173 道超配额 v2.1 菜谱和 4 道第 1 波菜谱，第一次构建时被
美国菜 20% 上限挡下，这次总数变大后上限不再卡住它们。合并估计的"覆盖"只算两波的菜谱数。

## 文件

- `sample.json`：抽样记录。固定种子 20261104，从第 2 波菜谱里抽 30 道。
- `review.xlsx`：发给复核人的空表，"你确认的过敏原""备注""已亲自核对"几栏是空的。

`sample.json` 和 `review.xlsx` 由 `python -I -X utf8 data-engineering/scripts/allergen_review.py draw --wave 2` 生成（仓库根目录，
离线，需要 openpyxl）。复核人交回后，把表存为 `review-filled.xlsx`，用
`python -I -X utf8 data-engineering/scripts/allergen_review.py score --wave 2 data-engineering/docs/allergen-review-20261104/review-filled.xlsx`
生成 `report.md` 和 `report.json`，不要手改。第 1 波的表也交回后，加上
`--with data-engineering/docs/allergen-review-20261103/review-filled.xlsx`，报告会多一节"Both waves"：两波的每一层
（波 × 过敏原）各带 Wilson 区间，再按每层的菜谱数加权给出两波合并的一致率（点估计）。第 1 波交回的表只读不改。
测试 `data-engineering/tests/test_review_draws_v3.py` 检查提交的样本就是重新抽出的样本。
