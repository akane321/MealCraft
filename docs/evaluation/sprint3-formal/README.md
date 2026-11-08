# Sprint 3 formal evaluation

The one run of the 280-question held-out set, at commit `b7538434` with anchor date 2026-10-23 and scoring
`formal-outcome-v2` (ADR-0120, ADR-0122). All files here are aggregates; per-case records stay outside the repository.

| File | What it holds |
| --- | --- |
| `aggregate-action.json` | Did each system take the right action (plan, ask, refuse) |
| `aggregate-action-no-catalog.json` | The same, leaving out questions whose right answer depends on the catalog |
| `aggregate-strict.json` | Stricter scoring; only 23 intent questions can be scored this way |
| `aggregate-plan.json` | Quality of the plans each system produced |
| `comparison-*.json` | Bootstrap comparisons of MealCraft against each other system |
| `manifest.json` | Arms, answers, digests and spend of the run |
| `freeze-record.txt` | What was frozen before the run |

The spend ledgers are in `docs/evaluation/baselines/`.

## Conditions of this run

- The project owner operated the run without opening the question file. This differs from the test-set statement, which
  named the question author as operator (ADR-0122).
- The halal answers were checked as reported by the owner; the development side did not see that check.
- AI-made decisions in the data repair and the added prices still need a human spot-check, and the tag batch was not
  accepted.
- The general-agent arm stopped at the runner's default limit of 3,000,000 tokens with 3 questions left, not at its
  spending cap. Those 3 were answered in a second command at the same commit, with the limit raised to 3,200,000.
- `mealcraft/ablation/rule_only_parser` answered 269 of 280 questions; 11 calls failed.
