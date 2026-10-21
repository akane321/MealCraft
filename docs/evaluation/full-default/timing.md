# Full default: plan wall time

> Scope: the cases of `latest.md`, one machine. The report's run lets the variety pass finish (and warms the candidate cache); the warm runs plan as the product does, the variety pass cut at its two seconds. Median and slowest of the warm runs. ADR-0079 sets how long is acceptable by how hard the request is: a simple request should still come back within about 4 s, a complex one may take up to about 60 s, and only past that is a case marked over. A case is never cut short to meet either figure, and no feature is dropped to make one faster.

Machine: Intel64 Family 6 Model 198 Stepping 2, GenuineIntel (Windows). The code commit is in `timing.json` beside this file.

| Case | Report run (s) | Warm median (s) | Warm max (s) | Against the ADR-0079 guidance |
|---|---:|---:|---:|---|
| one-adult | 8.42 | 5.38 | 5.73 | within the guidance for a complex request |
| four-with-vegetarian | 23.06 | 22.83 | 22.9 | within the guidance for a complex request |
| six-tight-budget | 162.07 | 77.01 | 83.5 | over ~60 s |
| two-no-oven-ten-days | 6.72 | 6.91 | 7.01 | within the guidance for a complex request |
| seven-with-young-children | 10.16 | 10.24 | 10.92 | within the guidance for a complex request |

Over ~60 s: six-tight-budget.

- `one-adult` (within the guidance for a complex request): one week-long beam search; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 40% of the run and reading the candidates (recipes and fixture prices) about 25%; at three meals a day for seven days that is 21 slots of combinations.

- `four-with-vegetarian` (within the guidance for a complex request): one beam search, three-quarters of the run; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 63%, and a third of the run is `member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per member and recipe). The vegetarian member's own candidates add up to 40 dishes a kind to the packet (`product_path._packet_covering`), so a meal has more combinations to check than before the shared-dish model.

- `six-tight-budget` (over ~60 s): four whole-week beam searches instead of one, 94% of the run: the ranked search keeps no week filled with no dish twice under the budget, so the three budget-led searches (`product_path.limit_led`, about 64%) run as well. Each builds every six-dish dinner of its candidates again; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 78% of the run, and `member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per member and recipe) is about 44%. The variety pass is about 5%. Upgrade path: share the meal checks between the four searches (they do not depend on the ranking) and cache the member checks. The owner accepted this case's time (ADR-0079 section 5, ADR-0080): over the line is a known exception, not a failure.

- `two-no-oven-ten-days` (within the guidance for a complex request): one beam search over ten days and two shopping trips, about two-thirds of the run; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 42%, and reading the candidates about 15%; the plan has 30 slots of combinations to build.

- `seven-with-young-children` (within the guidance for a complex request): one beam search, 80% of the run, over seven-dish dinners for a household of seven; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 69%, and `member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per member and recipe) about 37%.
