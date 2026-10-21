# Full default: plan wall time

> Scope: the cases of `latest.md`, one machine. The report's run warms the candidate cache; the warm runs are the same plan again. Median and slowest of the warm runs. ADR-0079 sets how long is acceptable by how hard the request is: a simple request should still come back within about 4 s, a complex one may take up to about 60 s, and only past that is a case marked over. A case is never cut short to meet either figure, and no feature is dropped to make one faster.

Machine: Intel64 Family 6 Model 198 Stepping 2, GenuineIntel (Windows). The code commit is in `timing.json` beside this file.

| Case | Report run (s) | Warm median (s) | Warm max (s) | Against the ADR-0079 guidance |
|---|---:|---:|---:|---|
| one-adult | 6.35 | 3.99 | 4.46 | quick |
| four-with-vegetarian | 18.52 | 18.75 | 19.53 | within the guidance for a complex request |
| six-tight-budget | 146.35 | 146.43 | 146.98 | over ~60 s |
| two-no-oven-ten-days | 5.64 | 5.48 | 8.74 | within the guidance for a complex request |
| seven-with-young-children | 8.49 | 8.48 | 9.01 | within the guidance for a complex request |

Over ~60 s: six-tight-budget.

- `four-with-vegetarian` (within the guidance for a complex request): one beam search, three-quarters of the run; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 63%, and a third of the run is `member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per member and recipe). The vegetarian member's own candidates add up to 40 dishes a kind to the packet (`product_path._packet_covering`), so a meal has more combinations to check than before the shared-dish model.

- `six-tight-budget` (over ~60 s): four whole-week beam searches instead of one, and a variety pass over 16 starts that no longer stops at two seconds (ADR-0080). In a profiled warm run of 2026-10-21, after that cutoff was removed, the variety pass (`product_path._vary_starts`) is about 50% of the run and the three budget-led searches (`product_path.limit_led`, which run because the ranked search keeps no week filled with no dish twice under the budget) about 33%; the ranked search and the setup are the rest. Across the run building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 46%, and `member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per member and recipe) is about 43%. Upgrade path, none of it changing a plan: make the variety pass faster (now the largest single cost), share the meal checks between the four searches (they do not depend on the ranking) and cache the member checks. The owner accepted this case's time (ADR-0079 section 5, ADR-0080): over the line is a known exception, not a failure.

- `two-no-oven-ten-days` (within the guidance for a complex request): one beam search over ten days and two shopping trips, about two-thirds of the run; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 42%, and reading the candidates about 15%; the plan has 30 slots of combinations to build.

- `seven-with-young-children` (within the guidance for a complex request): one beam search, 80% of the run, over seven-dish dinners for a household of seven; building each meal's dish combinations and checking every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `meal_composition.real_meal_issues`) is about 69%, and `member_coverage.member_can_eat` (asked again for every member, dish and combination, with nothing cached per member and recipe) about 37%.
