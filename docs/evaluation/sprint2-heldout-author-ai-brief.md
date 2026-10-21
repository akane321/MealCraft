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

Coordinator means a non-owner teammate who copies files without seeing questions.
The quota approver differs from author and reviewer; nobody reviews their own gold.
“协调人”是只复制文件、不看题目的非 owner 组员；配额审批人不能兼任出题人或复核人，
逐题复核人不能是出题人本人。

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
tofu, egg or legumes; it is not necessarily meat. Default dish counts may omit
at most one dish when budget, time or available dishes cannot fit it;
explicitly requested counts are fixed.
Snacks, sauces, drinks, desserts, salad alone or soup alone are not a complete
lunch/dinner. Protein mains in the same meal must not repeat protein sources.

MealCraft 帮助家庭表达需求、排餐、换菜或改餐型，并生成计入包装数量的购物清单。
成员各有饮食、忌口、过敏原和小数份量；规划支持单餐、一天或任意起始日的 1–14 天。
用户可明确减少餐次或菜数；否则按上表和三餐默认结构安排。午晚餐有主食，一锅出可以
兼任主菜和主食；豆腐、蛋、豆类也可作蛋白主菜。默认菜数在预算、时间或菜品放不下时最多少一道，
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

A plan longer than seven days shops before day 1 and day 8. The weekly budget
applies **separately to each trip**, including a shorter final period. Leafy
greens, bean sprouts and pea shoots, fresh fish and fresh shellfish must be used
within three days of their supplying trip; fresh meat is not in this short-lived
class. Do not assume one purchase for ten days or an extra fresh restock.
Record these defaults even
when the user has not repeated them.

预算按已知储藏室扣减后的整包购买计算，不只按用量计价；数量未知的在家食材不能扣减。
基础调料可已备或缺货，但仍参与营养和过敏原计算。价格有来源、时间与不确定性。
营养是按成员和计划餐次的估算，用户明确启用的钠等上限才是硬约束；普通偏好不自动变成
医学处方。数值参考、餐次分配须来自独立审核冻结的资料包，不能猜。医学治疗不在范围内。
用户可以问食物问题、表达偏好、换菜、改餐型或预算后重排；无关请求应拒绝，信息不明应追问。

超过七天分两次采购，分别在第 1 天前和第 8 天前；**每次采购各自满足每周预算**，
第二段不足七天也如此。绿叶菜、豆芽和豌豆苗、鲜鱼、鲜贝类在供应它们的那次购买后三天内
做掉；鲜肉不属于这类短保食材。十天不能按一次采购算，也不暗加中途鲜品补货。
用户没重述这些默认规则，仍须写入约束。

This is the intended evaluation scope, not a claim that a release has passed.
Do not seek implementation details or weaknesses. Shared-member diets, attendance,
halal and per-person avoidance describe accepted design decisions (including
ADR-0071), not necessarily text in today's user guide. Before handing this brief
to the author, the non-owner coordinator must verify it against the frozen
release's guide without looking at questions; pause if scope is not confirmed.
这是评测范围，不是验收结论；不获取实现细节或缺陷。合菜成员饮食、在场、清真与“仅本人回避”
来自包括 ADR-0071 在内的已接受设计决定，不是声称今天的用户指南已经写全。
交给出题人前，由非 owner 协调人对照冻结版本用户指南核对；未确认就暂停，不看题排查。

### Frozen reference facts v1 / 冻结参考事实 v1

Facts supplied here are the user-facing meal-count table above, default omission
of at most one dish, 1–14 days, two trips before days 1/8, separate weekly caps,
and a three-day perishability window. An **enabled** adult sodium limit defaults
to 2,000 mg/person/day; dinner uses 35%, so dinner-only means 700 mg/person/dinner,
including seasonings. Without opt-in, do not invent a hard sodium cap. These
facts derive from the product user guide; they are not recipe, package or price
data and do not prove that a requested plan is feasible.

本节给出的冻结用户事实：上表人数／菜数、默认最多少一道、1–14 天、1／8 日前各采购一次、
每次各自满足周预算、易腐三天内用完。成人**启用**钠上限后默认每天每人 2,000 mg，
晚餐占 35%，即只排晚餐时每人每顿 700 mg（含调料）；未启用则不擅自加硬上限。
这些来自用户指南，不包含菜谱、包装和价格，不能据此证明具体计划可行。

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
`horizon_1`, `horizon_14`, `two_trips`, `perishable_window`. At least two planning
cases must cover 8–14 days, with the exact long-horizon coverage predeclared.
`two_trips` and `perishable_window` are allowed only with `horizon_days > 7`;
`horizon_1` requires exactly 1 day and `horizon_14` exactly 14 days.
Include actual 1-day and 14-day cases, arbitrary start
days and explicitly smaller shapes. No realistic examples are provided here.

每类都含中英文，事先写好中文最低数；混合语言按句子主体判断，不靠翻译重复题凑数。
规划覆盖人数、不同松紧预算、过敏原组合、饮食／清真、餐型、时间、营养与在家食材。
上述十一个 feature 都预登记正数最低覆盖；至少两道规划题为 8–14 天，预先登记具体数量。
`two_trips`、`perishable_window` 只用于超过七天的题；`horizon_1` 必须恰为一天，
`horizon_14` 必须恰为十四天。
真实覆盖 1 天、14 天、任意起始日与缩小餐型。
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
| `quota_manifest` | `declared_on`: YYYY-MM-DD or null; `approved_by`: anonymous ID distinct from author/reviewer, or null; `fields_sha256`: 64 lowercase hexadecimal SHA-256 of dictionary bytes (null only in an unfinished template); `counts`, `minimum_chinese`: four category keys, integer ≥0 or null; `forum_count`: integer or null; `subtype_minima`, `feature_minima`: declared positive counts |
| Each case / 每题 | `id`: unique letters/digits/underscore/hyphen; `category`: one of four; `language`: `en` or `zh`; `subtype`: string; `features`: unique string list; `horizon_days`: integer 1–14 or null for non-planning; `turns`: nonempty ordered user-turn strings; `gold`: object; `source`: object |
| `gold` | `kind`: `plan` / `intent` / `qa` / `replan` / `refusal`; `disposition`: `feasible` / `infeasible` / `catalog_dependent` / `clarify` / `answer` / `refuse`; `hard_constraints`: constraint list; `expected_fields`: dictionary-typed object with mandatory `action`; `clarification_fields`: string list; `reference_answer`: string (may be empty when not QA); `rubric`, `preserve`: unique string lists; `proof_basis`, `facts_version`: nonempty strings; `review_status`: `pending` / `independently_checked`; `reviewer_id`: string or null, never the author |
| Each hard constraint / 硬约束 | `field`: dictionary field key; `operator`: `eq` / `le` / `ge` / `exclude` / `include`; `value`: matching dictionary type; `unit`: one of that field's units; `scope`: dictionary scope key; `evidence`: nonempty string; optional `target_member_ids`: nonempty unique string list, required for member scope |
| `source` | `kind`: `authored` / `forum`; `quotes`: quote list (empty for authored); `pii_reviewed`: boolean |
| Each quote / 每条原话 | `turn_index`: zero-based integer; `text`: exact redacted turn; `url`: canonical public http(s) thread/comment URL without tracking query/fragment; `collected_on`: YYYY-MM-DD; `redactions`: unique strings describing categories removed, never actual personal values |

Only these kind/disposition pairs are allowed / 只允许以下题型与处置值搭配：

| `gold.kind` | Allowed `disposition` / 允许的处置值 |
|---|---|
| `plan` | `feasible`, `infeasible`, `catalog_dependent`, `clarify` |
| `replan` | `feasible`, `infeasible`, `catalog_dependent`, `clarify` |
| `intent` | `answer`, `clarify`, `refuse` |
| `qa` | `answer`, `clarify`, `refuse` |
| `refusal` | `refuse` |

For `intent`, `answer` is the structured classification/extraction answer, not
planning feasibility. `le` and `ge` values must be numeric, not booleans,
strings, arrays or objects; dictionary type/unit checks also apply.
`intent` 的 `answer` 指结构化分类／抽取答案，不表示排餐可行。
`le`、`ge` 的值必须是数字，不能是布尔、字符串、数组或对象，同时仍须符合字典类型和单位。

`sprint2-heldout-fields.json` is the neutral dictionary, not the application's
internal schema. Unknown fields or wrong types/units/scopes fail validation.
Missing facts are omitted and named in `clarification_fields`, not guessed or
represented by arbitrary nulls (unknown pantry quantity explicitly permits null).
The author/reviewer may extend inline types before freeze, update the dictionary
version, and put its exact-byte digest in `fields_sha256`. Never rename fields
after questions are frozen. A later adapter uses this dictionary without seeing cases.

中立字典是 `sprint2-heldout-fields.json`，不是应用内部 schema。未知字段、错误类型／单位／
范围不能通过。缺失事实不猜，省略并在 clarification_fields 中点名；不随意填 null，
只有明确定义的未知储藏量允许 null。出题人与复核人可在冻结前扩充内联类型、更新字典版本、
填写原始字节指纹 fields_sha256；冻结题目后不得改名，未来适配器只依字典工作而不看封存题。

| Neutral fields / 中立字段 | Types and meaning / 类型与含义 |
|---|---|
| `action` | required string: plan, swap, change_meal_structure, change_budget, food_qa, record_preference, clarify, refuse |
| `request_scope`, `start_date`, `horizon_days`, `household_size` | meal/day/week/range; YYYY-MM-DD; integer 1–14; positive integer / 范围、日期、天数、人数 |
| `members` | list of member_id with optional age_band (toddler/child/teen/adult/older_adult/unknown), sex (female/male/unknown), positive decimal portion_factor, dietary_requirements/allergens/excluded_ingredients string lists |
| `meal_types`, `attendance` | unique breakfast/lunch/dinner list; attendance rows with date, meal_type, absent_member_ids / 餐次及具体缺席成员 |
| `meal_structure` | breakfast/lunch/dinner maps: nonnegative integer protein_mains, vegetables, soups, staples, breakfast_dishes; boolean counts_explicit |
| `weekly_budget_sgd`, `budget_basis`, `shopping_trip_days`, `perishable_window_days` | nonnegative SGD; per_shopping_trip; unique integer day numbers 1–14 (long plans [1,8]); fixed 3 |
| `sodium_limit_enabled`, `sodium_limit_mg`, `dinner_sodium_share` | boolean; nonnegative mg scoped by constraint; fraction 0–1 (reference dinner share 0.35) |
| `allergens`, `dietary_requirements`, `excluded_ingredients`, `allergen_avoidance_scope`, `halal_required` | string lists; household/member avoidance scope; boolean halal requirement |
| `basic_seasonings`, `pantry` | available/run_out string lists; pantry rows with ingredient, quantity (nonnegative or null), unit g/ml/count/unknown |
| `cooking_time_minutes`, `maximum_repeats`, `preferences` | nonnegative minutes; nonnegative integer occurrences; string list of soft preferences |
| Constraint scope / 约束范围 | household, member (target_member_ids required), meal, day, week, trip, plan |

Units are fixed by field: people, date, days, SGD, day_numbers, mg, fraction,
minutes, occurrences, dishes, or none; consult the copied dictionary's units.
Schema references (`$ref`, `$dynamicRef`) are forbidden in extensions; inline
definitions only. For long horizons record shopping_trip_days=[1,8],
budget_basis=per_shopping_trip and perishable_window_days=3.
This applies to plan/replan gold, not extra extracted fields for intent-only gold.
单位必须用字典规定值，扩展不允许 $ref 或 $dynamicRef，只能用内联定义；长周期明确记录
1／8 日两次采购、每次周预算和三天窗口。规划 subtype 用 plan；多轮用 replan；理解分类用
intent；food_qa 可用 qa；越界／注入可用 refusal。其他对抗题按任务本质用 plan、intent 或 qa，
不能把改餐型标成问答等不匹配的 kind。
派生采购规则写在 plan／replan 的答案中；只测意图抽取时不强加用户未说的采购字段。

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
For planning that depends on unavailable recipe/product/price facts, use
`catalog_dependent`, write hard constraints and note that catalog adjudication
is pending in proof_basis. The author need not prove feasibility. Only an
intrinsic logical contradiction in the request is labelled infeasible here,
with a catalog-independent proof. A timeout is not proof. After freeze, a
separate independent sealed process will adjudicate against the frozen catalog;
it is not implemented by this toolkit and must not derive gold from the product
being evaluated. State nutrition units/person/time scope and opt-in limits.
Unclear user facts may require clarification; do not confuse them with missing catalog data.
QA rubrics distinguish required claims, acceptable alternatives, unsupported
claims and appropriate abstention. Gold is independently checked by the reviewer.

标准答案不来自系统输出。依赖未提供的菜谱／商品／价格时标 catalog_dependent，只写硬约束，
proof_basis 写明待目录判定，出题人不证明可行。只有请求自身的逻辑矛盾才在这里标无解，
并给不依赖目录的证明；超时不算证明。冻结后由另行实现的独立封闭流程根据冻结目录判定，
本工具包不实现，且不能用被评产品的成败当答案。营养明确单位／成员／范围和主动上限。
用户没说清的保留歧义并追问，不把缺目录事实误当用户漏说。
问答区分必要要点、可接受替代表述、禁止无依据断言和何时应保留判断；由另一人独立检查。

Collect minimal relevant **public** forum wording, not rewritten imitations.
Keep original wording/tone; remove handles, contact details, identifiable places
and unrelated text with `[REDACTED]` markers; record canonical URL, date and
redaction categories. Nonempty redaction notes require `[REDACTED]` in the text
and vice versa. Remove plain u/handles and @handles as well as profile URLs.
Do not invent missing facts or follow-up turns. For forum cases every user turn
must exactly match its redacted quote and have a unique
source record; otherwise classify the construction as authored, outside the
forum quota. Respect site rules; the reviewer checks re-identification risk.
Do not send URLs or quotes to developers. Public availability is not blanket
permission to republish personal details.

从公开论坛收集最少必要原话，不改写成仿真句；保留语气，删除用户名、联系方式、可识别地点
和无关片段，用 `[REDACTED]` 标明，并记来源、日期、删除类别。不补全没说的信息，不捏造
后续对话。论坛题每个用户回合都与脱敏原话一致且有唯一来源；混入自编回合就按 authored
计，不占论坛配额。遵守站点规则，复核再识别风险；链接和原话不发开发者。
也删 u/用户名、@用户名；有 redactions 记录的原话须有 [REDACTED] 标记，反之亦然。

## 6. Check, review and freeze / 检查、复核、冻结

Have the coordinator copy only these standalone files into your folder:
`check_sprint2_heldout.py`, `sprint2-heldout.schema.json`,
`requirements-sprint2-authoring.txt`, `sprint2-heldout-template.json` (empty),
`sprint2-heldout-fields.json`. Script, schema and dictionary stay adjacent. Do not clone or browse the repository to
obtain them. Install the declared standalone dependency and explicitly select
your own file. No network/model call occurs during checking.

非 owner 协调人只复制上述五个独立文件到出题目录，脚本、schema 和字典相邻；模板为空。
不要为获取它们去克隆或浏览仓库。安装声明的独立依赖，显式指定自己文件；检查不联网或调用模型。

```text
python -m pip install -r requirements-sprint2-authoring.txt
python check_sprint2_heldout.py --input author-draft.json --format-only
python check_sprint2_heldout.py --input author-draft.json
python check_sprint2_heldout.py --input author-draft.json --fields sprint2-heldout-fields.json
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
time, byte count, format/reference versions, field-dictionary SHA-256 and original
quota-manifest digest. Store both exact files read-only. Send contents only to the authorised sealed automated
run; developers receive the manifest, not cases. Do not run an evaluation here.
All systems later use the same frozen set in one pre-registered formal campaign,
with repeats fixed in advance. Frozen questions/gold are immutable; mistakes
can only be voided in a separate append-only, digest-linked ledger, consistently
for every system. Never repair labels after seeing outcomes for a better score.

人工独立确认后记录文件原始字节的 SHA-256、UTC 时间、字节数、版本、字段字典和原配额指纹，
题目与字典的原始字节一起只读保存，不能重新格式化后还沿用旧指纹。
内容只交授权的封闭自动运行流程，开发者只收清单。本对话不跑评测。之后所有系统在同一冻结
集上按预登记次数完成一次正式评测活动。冻结后不改题面或答案；错题只在指纹关联的追加记录
中作废，对全部系统一致处理，不看成绩改标签。
