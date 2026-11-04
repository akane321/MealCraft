# Baseline arms on the conversation protocol

This is apparatus for issue #396 and `operations/sprint2-plan/02-baselines.md` of the Knowledge repository,
**not a freeze, a run admission or a result**. It rebuilds the RAG, general-agent and strong-rule arms so that
they answer through the ADR-0092 conversation harness (`backend/app/evaluation/conversation_adapter.py`) like the
product does, and are scored by the unchanged shared layers.

## What every arm gets

- The user's own strings, in order, and its own earlier exchanges. Never an episode's gold, category, household
  profile, pool or products (`baseline_arms.episode_turns`).
- The shared instructions and the one fixed confirmation message of the harness, under one global anchor date
  (`--anchor-date`).
- Its own registered configuration, and nothing else:

| Arm | Module | Configuration | Paid |
| --- | --- | --- | --- |
| `strong-rule` | `strong_rule_baseline.py` | No model. The product's rule parser and `plan_dates`, keyword rules for each meal's dishes, catalog filters (meal type, course, time, allergens, exclusions with the ingredient hierarchy, diet, halal), and a fixed cheapest-first priority with per-role energy and protein floors and the product's vegetable-led rule | no |
| `rag` | `rag_baseline.py` | The release v3 recipes most similar to the request (the recipe vectors `data/recipes/embeddings-v1.json` and `.bin`, `PER_GROUP` per course group), listed with frozen-snapshot cost estimates; the model plans | yes |
| `general-agent` | `general_agent_baseline.py` | OpenAI hosted web search and a calculator only, no MealCraft catalog or prices (owner, 2026-11-03 on #396) | yes |

The pure-LLM arm keeps its own single-turn runner (`pure_llm_baseline.py`).

## Scoring

The final output of a case becomes the ingredient-level `BaselineResponse`: each dish's ingredient lines, steps
and time come from its `evidence`, and a meal's date and meal type become a `mon-dinner` slot. The record is then
scored by `pure_llm_baseline.score` (mapping, coverage, recomputation, allergen safety, the product validator).
A dish without ingredient lines makes the output invalid; it is never read as an infeasible answer. No shared
scoring code is changed here.

## Cost (ADR-0086)

A paid arm makes no call without `--live`. The default is a dry run that prints each case's worst case with no
network. A live run checks every call against `--max-usd` (default US$5) and `--max-tokens` at its worst case
before it is made, charges the tokens the API reports, and counts what earlier runs into the same output spent.
The general-agent arm also charges every web search at an upper estimate (`SEARCH_USD`, `SEARCH_BLOCK_TOKENS`);
confirm both on the OpenAI pricing page before a run. Since the US$5 is the arm's total, each live run's
`--max-usd` is what that arm's earlier outputs left of it.

## Commands

From `backend/`, on the development episodes only (a held-out path is refused without `--allow-heldout`):

```bash
python -m app.evaluation.baseline_arms --arm strong-rule \
  --episodes data/evaluation/dev/v3-meal-day-week/episodes --anchor-date 2026-09-28 \
  --output docs/evaluation/baselines/dev/strong-rule.jsonl
python -m app.evaluation.baseline_arms --arm rag \
  --episodes data/evaluation/dev/v3-meal-day-week/episodes --anchor-date 2026-09-28 \
  --output docs/evaluation/baselines/dev/rag.jsonl            # dry run; add --live --max-usd to pay
python -m app.evaluation.baseline_arms --arm general-agent --fingerprint   # the freeze fingerprint
```

Each output is JSONL, one record per case and repeat, with a `.report.json` beside it. Its records are what the
mapping review reads ([baseline-mapping-review](baseline-mapping-review/README.md)).

## Known limits

- The strong-rule arm does not read nutrition targets, and its cost order is per gram of the cheapest package,
  not whole packages; the scorer recomputes the real purchase.
- The RAG candidates are retrieved by similarity only and are not filtered by the household's limits.
- The web-search prices are upper estimates from public reports, not confirmed figures.
