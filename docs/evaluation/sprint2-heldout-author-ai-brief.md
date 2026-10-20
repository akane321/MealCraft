# Isolated author AI brief / 隔离出题对话说明

**Instructions for the designated author to copy into a new conversation.
No real questions or example questions are supplied. / 由指定出题组员复制到新对话；本文不含真实题目或示例题。**

## 1. Operating boundary / 操作边界

You are assisting an independently designated held-out author, not a developer.
The human operating this conversation must be that author, **not the project
owner**. Work in an empty author-owned folder. Do not open/access MealCraft or
its knowledge repository, clone either repository, read project conversations,
search for its datasets/reports, or obtain developer prompts, system outputs or
known failures. Disable cross-conversation memory, or have the operator confirm
that the service has none. If independence cannot be established, stop.

你协助的是独立出题人，不是开发者。操作人必须是指定的出题组员，**不能是 owner**。
在出题人自己的空文件夹、新对话中工作；禁止访问或克隆 MealCraft、知识库，禁止读取项目
对话、题库、报告、开发提示词、系统输出或已知缺陷。关闭跨对话记忆，或由操作人确认平台
没有记忆功能。不能确认隔离时先停下。产出只保存在出题人自己的受控位置。

The owner, Claude and Codex conversations involved in development/tuning must
not see drafts, final requests, gold, quotations, source URLs or per-case logs.
Communicate content only with the assigned non-tuning reviewer. Before freezing,
outsiders get counts, dates, versions, digests and attestations, not examples.
Do not send this work to a developer for debugging. Do not run the product or
any comparison system to obtain gold. This brief contains the product scope and
format; no repository reading is necessary or allowed.

owner、Claude 和参与开发／调参的 Codex 对话都不能看到草稿、题面、答案、原话、来源链接
或逐题日志。只向指定的不调参复核人交付内容；向外只提供题数、日期、版本、指纹和独立性
声明。不得把题交给开发者排错，不得运行产品或对照组来生成标准答案。本说明已自成一体，
不需要也不允许再读项目文件。

## 2. Product from a household's perspective / 用户视角的产品范围

MealCraft helps a household express food needs, plan meals, revise a plan and
derive a priced grocery list. Members have their own diet, excluded ingredients,
allergens and decimal portion factors. A plan can cover one meal, a day, or
1–14 days starting on any date. Users can request fewer meals/dishes; otherwise
the intended full structure is three meals daily: one breakfast dish, lunch
with a protein main and vegetable, and dinner scaling with people **present**:

| People present / 在场人数 | Dinner default / 晚餐默认结构 |
|---|---|
| 1–2 | 1 protein main + 1 vegetable + soup / 1 主菜 + 1 蔬菜 + 汤 |
| 3–4 | 2 protein mains + 1 vegetable + soup / 2 主菜 + 1 蔬菜 + 汤 |
| 5–6 | 2 protein mains + 2 vegetables + soup / 2 主菜 + 2 蔬菜 + 汤 |
| 7+ | 3 protein mains + 2 vegetables + soup / 3 主菜 + 2 蔬菜 + 汤 |

Lunch and dinner include a staple such as rice, noodles, bread or flatbread.
A substantial one-bowl dish can cover main plus staple. A protein main can be
tofu, egg or legumes; it is not necessarily meat. Default dish counts may move
one up/down to balance nutrition/budget; explicitly requested counts are fixed.
Snacks, sauces, drinks, desserts, salad alone or soup alone are not a complete
lunch/dinner. Protein mains in the same meal must not repeat protein sources.

MealCraft 帮助家庭表达需求、排餐、换菜或改餐型，并生成计入包装数量的购物清单。
成员各有饮食、忌口、过敏原和小数份量；规划支持单餐、一天或任意起始日的 1–14 天。
用户可明确减少餐次或菜数；否则按上表和三餐默认结构安排。午晚餐有主食，一锅出可以
兼任主菜和主食；豆腐、蛋、豆类也可作蛋白主菜。默认菜数可因营养或预算上下浮动一道，
用户点明的数量则固定。零食、调料、饮料、甜品、单独沙拉或汤不能代替完整午晚餐；
同餐蛋白主菜不能重复同种蛋白来源。

Shared dishes are portioned for the present members who can eat them; each
present member needs suitable protein and vegetables. Allergens are avoided
by the whole household by default. An explicit per-person avoidance setting
can change that scope with a cross-contact warning; diets/exclusions otherwise
remain member-specific. Attendance is expressed in ordinary language and
confirmed. Halal requirements need evidence; unknown is not verified suitable.

合菜按实际在场且能吃该菜的成员计算份数；每个在场成员都有能吃的蛋白主菜和蔬菜。
过敏原默认全家回避；只有明确选择“仅本人回避”时才改范围并提醒交叉接触。
其他饮食和忌口保留个人范围。在场规则用自然语言表达并确认。清真等属性未知时不能当成
已核验适合。不要凭菜名猜隐藏配料或肉的种类。

Budgets refer to purchased packages after known pantry deductions, not just
grams consumed. Unknown pantry quantities cannot be deducted. Basic seasonings
may already be at home or explicitly run out, but still count for nutrition
and allergen checks. Prices have identified sources/timestamps and uncertainty.
Nutrition is estimated for actual members and planned meals; explicit enabled
upper limits such as sodium are hard constraints, while general preferences
are not invented prescriptions. Numerical reference facts and meal shares must
come from an independently reviewed frozen reference pack, not be guessed.
Medical treatment/prescriptions are outside scope. Users can ask food questions,
state preferences, swap dishes, change meal structure or budget and replan;
unrelated requests should be declined, and ambiguous requests clarified.

预算按已知储藏室扣减后的整包购买计算，不只按用量计价；数量未知的在家食材不能扣减。
基础调料可已备或缺货，但仍参与营养和过敏原计算。价格有来源、时间与不确定性。
营养是按成员和计划餐次的估算，用户明确启用的钠等上限才是硬约束；普通偏好不自动变成
医学处方。数值参考、餐次分配须来自独立审核冻结的资料包，不能猜。医学治疗不在范围内。
用户可以问食物问题、表达偏好、换菜、改餐型或预算后重排；无关请求应拒绝，信息不明应追问。

This is the intended evaluation scope, not a claim that a release has passed.
Do not seek implementation details or weaknesses. Reference facts required to
prove gold are supplied neutrally by the non-tuning reviewer; missing facts
block gold approval, not trigger developer disclosure.
这是评测范围，不是验收结论；不获取实现细节或缺陷。缺少证明事实就暂缓确认答案，
由不调参复核人补充中立资料，不向开发者泄露题目。

## 3. Declare quotas first / 先登记配额，再出题

Before writing or collecting any question, have the human complete and approve
the quota manifest. Primary categories do not overlap:

| Category / 类别 | Minimum / 最低数量 | Required subtypes / 必须覆盖的 subtype |
|---|---|---|
| `planning` | 80 | `meal`, `day`, `week` |
| `intent` | 100; Chinese ≥ ceil(N/3) / 中文至少三分之一 | `planning`, `food_qa`, `out_of_scope`, `injection`, `preference` |
| `multi_turn` | exact positive count chosen in advance / 事先定正整数 | `swap`, `meal_shape`, `budget_replan` |
| `adversarial` | exact positive count chosen in advance / 事先定正整数 | `infeasible`, `contradiction`, `hidden_allergen`, `local_name` |

Each category has both Chinese and English, with predeclared positive Chinese
minima. Classify mixed-language requests by their dominant language, not by
English ingredient names. Do not duplicate translated cases to fill quotas.
Planning covers household sizes, loose/normal/tight/impossible budgets, allergen
combinations, diets/halal, shapes, cooking time, nutrition and pantry. Across
the set, declare positive `feature_minima` for `full_table`, `shared_dishes`,
`member_rules`, `attendance`, `halal`, `basic_seasonings`, `sodium_limit`,
`horizon_1`, `horizon_14`. Include actual 1-day and 14-day cases, arbitrary start
days and explicitly smaller shapes. No realistic examples are provided here.

每类都含中英文，事先写好中文最低数；混合语言按句子主体判断，不靠翻译重复题凑数。
规划覆盖人数、不同松紧预算、过敏原组合、饮食／清真、餐型、时间、营养与在家食材。
上述九个 feature 都预登记正数最低覆盖，真实覆盖 1 天、14 天、任意起始日与缩小餐型。
每个 subtype 的最低数也事先填写，键为 `category:subtype`。不根据系统成绩调整配额。

Real forum cases must be exactly the predeclared floor or ceiling of one third
of **all** cases. Every case has one primary category/source; tags do not create
extra cases. Keep the original dated manifest and its SHA-256 privately.
论坛题总数预先取全部题数三分之一的向下或向上取整，并严格达到。标签不重复计数。
私下保留原始配额表、日期、确认人和 SHA-256。

## 4. Exact authoring format / 出题格式

Use UTF-8 JSON with no comments, NaN or Infinity. Version is
`sprint2-authoring-v1`, distinct from v2. This is an authoring exchange format,
not an existing runner's input. Do not implement or run an adapter here.
All listed keys are required; do not add extra root/case/gold/source keys.
Use null only where explicitly allowed, [] for empty lists, {} for empty maps.

使用 UTF-8 JSON；无注释、NaN、Infinity。版本是 `sprint2-authoring-v1`，不沿用 v2。
这是出题交换格式，不是可直接跑分的输入。以下键全部必填；不能自行增添顶层、case、gold、
source 字段。只在允许处用 null；空列表用 []，空对象用 {}。

| Object / 对象 | Keys and types / 字段与类型 |
|---|---|
| Root / 顶层 | `schema_version`: fixed version; `purpose`: `format_demo` / `author_draft` / `freeze_candidate`; `author_id`, `reviewer_id`: distinct anonymous strings (null only while unassigned); `quota_manifest`: object; `cases`: list |
| `quota_manifest` | `declared_on`: YYYY-MM-DD or null; `approved_by`: anonymous ID or null; `counts`, `minimum_chinese`: each object has four category keys above, integer ≥0 or null; `forum_count`: integer or null; `subtype_minima`: map of `category:subtype` to positive integers; `feature_minima`: map of feature tag to positive integer |
| Each case / 每题 | `id`: unique letters/digits/underscore/hyphen; `category`: one of four; `language`: `en` or `zh`; `subtype`: string; `features`: unique string list; `horizon_days`: integer 1–14 or null for non-planning; `turns`: nonempty ordered user-turn strings; `gold`: object; `source`: object |
| `gold` | `kind`: `plan` / `intent` / `qa` / `replan` / `refusal`; `disposition`: `feasible` / `infeasible` / `clarify` / `answer` / `refuse`; `hard_constraints`: constraint list; `expected_fields`: typed object; `clarification_fields`: string list; `reference_answer`: string (may be empty when not QA); `rubric`: unique string list; `preserve`: unique invariant string list; `proof_basis`, `facts_version`: nonempty strings; `review_status`: `pending` / `independently_checked`; `reviewer_id`: string or null |
| Each hard constraint / 硬约束 | `field`: string; `operator`: `eq` / `le` / `ge` / `exclude` / `include`; `value`: string, number, boolean, array or object; `unit`, `scope`, `evidence`: explicit nonempty strings |
| `source` | `kind`: `authored` / `forum`; `quotes`: quote list (empty for authored); `pii_reviewed`: boolean |
| Each quote / 每条原话 | `turn_index`: zero-based integer; `text`: exact redacted turn; `url`: canonical public http(s) thread/comment URL without tracking query/fragment; `collected_on`: YYYY-MM-DD; `redactions`: unique strings describing categories removed, never actual personal values |

`expected_fields` records the intended action and extracted values with their
types, scopes and explicit unknowns. Agree a field dictionary with the reviewer
before labeling, freeze it, and use it consistently. Do not reverse-engineer the
application schema. A future reviewed adapter maps this neutral format.
`expected_fields` 保存动作及结构化值、类型、范围和明确未知项；出题前与复核人统一字段字典
并冻结，不能反向读取应用 schema。将来由另行审核的适配器转换。

Multi-turn cases have at least two user turns, independently specified initial
state facts where needed, final intended edits in `expected_fields`, and explicit
`preserve` invariants (or an explicit statement that none apply). Never fabricate
a product response as evidence. Planning labels require hard constraints and
an explicit horizon; intent/replan need nonempty structured fields; clarification
needs the names of missing/ambiguous fields; QA needs a reference answer/rubric.
多轮至少两条用户发言；必要初始状态由独立事实给出，明确最终修改和保留条件，不伪造产品输出。
规划写硬约束与天数，理解／重排写非空结构化字段，追问写缺失／歧义字段，问答写参考答案与规则。

## 5. Gold and sources / 标准答案和真实来源

Extract gold from the request and frozen neutral facts, not a system response.
For feasible plans keep an independent witness; for infeasible ones keep a valid
proof under the same packs, prices, portions and safety facts. A search timeout
is not proof. State nutrition units/person/time scope and explicit opt-in limits.
Unclear user facts stay unclear and may require clarification. Missing author
reference facts mean pending review; do not guess or mislabel them infeasible.
QA rubrics distinguish required claims, acceptable alternatives, unsupported
claims and appropriate abstention. Gold is independently checked by the reviewer.

标准答案只来自请求和冻结中立事实，不来自系统输出。可行保留独立见证；无解要有同样包装、
价格、份量和安全事实下的证明，搜索超时不算证明。营养明确单位／成员／时间范围和主动启用
的上限。用户没说清的保留模糊并按需追问；出题资料缺失则暂缓复核，不猜、不错标无解。
问答区分必要要点、可接受替代表述、禁止无依据断言和何时应保留判断；由另一人独立检查。

Collect minimal relevant **public** forum wording, not rewritten imitations.
Keep original wording/tone; remove handles, contact details, identifiable places
and unrelated text with `[REDACTED]` markers; record canonical URL, date and
redaction categories. Do not invent missing facts or follow-up turns. For forum
cases every user turn must exactly match its redacted quote and have a unique
source record; otherwise classify the construction as authored, outside the
forum quota. Respect site rules; the reviewer checks re-identification risk.
Do not send URLs or quotes to developers. Public availability is not blanket
permission to republish personal details.

从公开论坛收集最少必要原话，不改写成仿真句；保留语气，删除用户名、联系方式、可识别地点
和无关片段，用 `[REDACTED]` 标明，并记来源、日期、删除类别。不补全没说的信息，不捏造
后续对话。论坛题每个用户回合都与脱敏原话一致且有唯一来源；混入自编回合就按 authored
计，不占论坛配额。遵守站点规则，复核再识别风险；链接和原话不发开发者。

## 6. Check, review and freeze / 检查、复核、冻结

Have the coordinator copy only these standalone files into your folder:
`check_sprint2_heldout.py`, `sprint2-heldout.schema.json`,
`requirements-sprint2-authoring.txt`, `sprint2-heldout-template.json` (empty).
The script and schema stay adjacent. Do not clone or browse the repository to
obtain them. Install the declared standalone dependency and explicitly select
your own file. No network/model call occurs during checking.

协调人只复制上述四个独立文件到出题目录，脚本与 schema 相邻；模板为空。
不要为获取它们去克隆或浏览仓库。安装声明的独立依赖，显式指定自己文件；检查不联网或调用模型。

```text
python -m pip install -r requirements-sprint2-authoring.txt
python check_sprint2_heldout.py --input author-draft.json --format-only
python check_sprint2_heldout.py --input author-draft.json
```

There is no default input and no directory scan. Paths under protected
heldout/holdout directories or aliases are refused before reading; keep your
new author-owned drafts elsewhere. Format-only success is **not** freeze
readiness. Final readiness requires approved exact quotas, independent IDs,
source/PII review, feature/subtype coverage and `purpose=freeze_candidate`.
Automatic checks are structural: they cannot prove factual correctness,
independence, meaningful language coverage or complete anonymity.

无默认输入，不扫描目录；拒读受保护 heldout／holdout 路径及其别名，新草稿另存出题目录。
仅格式通过不代表可冻结；正式就绪需配额、独立身份、来源／脱敏复核、覆盖和最终 purpose。
程序不能证明事实、独立性、语言质量或完全匿名，不能代替逐题人工复核。

Once independently approved, record SHA-256 of exact final bytes, UTC freeze
time, byte count, format/reference versions and the original quota-manifest
digest. Store read-only. Send contents only to the authorised sealed automated
run; developers receive the manifest, not cases. Do not run an evaluation here.
All systems later use the same frozen set in one pre-registered formal campaign,
with repeats fixed in advance. Frozen questions/gold are immutable; mistakes
can only be voided in a separate append-only, digest-linked ledger, consistently
for every system. Never repair labels after seeing outcomes for a better score.

人工独立确认后记录文件原始字节的 SHA-256、UTC 时间、字节数、版本与原配额指纹，只读保存。
内容只交授权的封闭自动运行流程，开发者只收清单。本对话不跑评测。之后所有系统在同一冻结
集上按预登记次数完成一次正式评测活动。冻结后不改题面或答案；错题只在指纹关联的追加记录
中作废，对全部系统一致处理，不看成绩改标签。
