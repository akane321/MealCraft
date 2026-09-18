# 数据来源与许可边界

## RecipeNLG

- 官方页面：<https://recipenlg.cs.put.poznan.pl/dataset>
- 用途：大型原始食谱池、食材字符串解析、NER 对照、清洗和抽样。
- 条款：仅限非商业研究和教育用途；下载者必须主动接受条款。
- 项目策略：上游完整数据集（约 164 万条）只保存在本地 `data/raw/`，不提交 Git；团队成员取得数据前均应了解条款。
- 经清洗、版本化的 release（`data/release/`）已提交本公开仓库：项目负责人已确认获得许可，且仅用于非商业教育用途。条款接受人在 `data/raw/recipenlg/raw_manifest.json` 中只记录贡献者角色，不记录个人姓名。
- 注意：RecipeNLG 中一部分记录来自 Recipe1M+，必须保留 `source` 字段。

## USDA FoodData Central

- 官方页面：<https://fdc.nal.usda.gov/>
- 用途：标准食品条目、每 100 g 营养信息、份量和重量参考。
- 许可：公共领域，CC0 1.0。
- 项目策略：保存 `fdc_id`、数据类型、检索词、检索时间和原始响应摘要。每条匹配记录候选、证据、置信度和被否决的备选（ADR-0024 第 1 节）；只有 `mapped` 状态写入 `fdc_id`，`needs_review` 不得当作事实使用。

## FoodOn

- 官方仓库：<https://github.com/FoodOntology/foodon>
- 用途：食材本体、层级、标准术语和同义词参考。
- 许可：CC BY 4.0。
- 项目策略：MealCraft 继续使用自己的稳定 ID；`foodon_id` 是外部映射，不取代内部 ID。

## Singapore Food Insights Database

- 官方页面：<https://www.hpb.gov.sg/healthy-living/food-and-beverage/sgfoodid/>
- 用途：新加坡常见食物、饮料和本地菜肴的营养交叉验证。
- 项目策略：在批量抓取或再发布前确认使用条款；第一轮不自动抓取。

## FairPrice

- 用途：商品标题、包装规格、价格、可售状态和观察时间。
- 项目策略：独立于食谱和营养参考库；不得把 Open Food Facts 当成 FairPrice 实时数据。

## 数据许可登记要求

每个外部源至少保存：

- `source_name`
- `source_url`
- `source_record_id`
- `source_license`
- `retrieved_at`
- `source_version`
- `transformation_version`

无法确定许可或来源的数据只能用于本地探索，不能进入公共发布包。

