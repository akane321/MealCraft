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
| `general-agent` | `general_agent_baseline.py` | OpenAI hosted web search (GitHub's domains blocked) and a calculator only, no MealCraft catalog or prices (owner, 2026-11-03 on #396); at most `MAX_STEPS` = 3 responses a turn and `MAX_SEARCHES` = 2 searches a response | yes |

The pure-LLM arm keeps its own single-turn runner (`pure_llm_baseline.py`).

## Scoring

The final output of a case becomes the ingredient-level `BaselineResponse`: each dish's ingredient lines, steps
and time come from its `evidence`, and a meal's date and meal type become a `mon-dinner` slot. The record is then
scored by `pure_llm_baseline.score` (mapping, coverage, recomputation, allergen safety, the product validator).
A dish without ingredient lines makes the output invalid; it is never read as an infeasible answer. No shared
scoring code is changed here.

## Cost (ADR-0086)

A paid arm makes no call without `--live`. The default is a dry run that prints the worst case with no
network, with what the arm's ledger already holds (`ledger_usd`); `fits_cap` is true only when both fit `--max-usd`.

**One spend ledger per arm.** A live run keeps the arm's append-only ledger (`--ledger`, default
`docs/evaluation/baselines/<arm>.spend.jsonl`), whatever the output file. Before every paid call, once
`--max-usd` (default US$5) and `--max-tokens` allow its worst case, a `reserve` line is written; when the call
returns, a `charge` line with its tokens and tool fees. A call the API refused unbilled (status 400, 401, 403, 404,
409, 422 or 429) is settled with a zero charge. A reserve that no charge follows (a timeout, a dropped connection,
a killed process) counts at its worst case. Every run starts from the ledger's total, so a case cut by the cap and
a crash are never lost, and the caps hold for the arm as a whole: the development trial runs with
`--max-usd 1.0`, the held-out run with `--max-usd 5.0`, and what the trial spent is already counted. The owner's
rule for the held-out run: run until the cap stops it, then stop and report on #396 before anything else (no higher
cap, new output, changed configuration or retried failures).

A case whose call failed is not asked again on a rerun unless `--retry-failed` is given, since it was paid for.

The general-agent arm charges each web search US$0.01 (the `web_search` tool, US$10 per 1,000 calls, for every
model) on top of the reported tokens; `SEARCH_BLOCK_TOKENS` is only the reserve for search content before a call.

**Held-out runs publish aggregates only** (#408, group 3). The development trial's ledger, records, search trace
and raw responses may be committed. For a held-out run the per-case records, search queries and sources and raw
responses stay local; its ledger lines carry no episode id, and only the summary is published. `--allow-heldout`
also refuses a checkout with uncommitted changes (untracked files included), and every report records `code_commit`
(`git rev-parse HEAD` of the checkout) and `worktree_dirty` (`git status --porcelain` of the same checkout). So:

- write a held-out run's `--output` under `.local/evaluation/` (ignored by git), never beside the committed development outputs;
- commit the development trial's ledger before the held-out run, and, if the owner lets a capped run go on, commit
  the ledger again before resuming.

The rules of this section are `ADR-0115` of the Knowledge repository, which amends ADR-0086.

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
python -m app.evaluation.baseline_arms --arm rag \
  --episodes data/evaluation/dev/v2-multidish/episodes --anchor-date 2026-09-28 \
  --output docs/evaluation/baselines/dev/rag-v2-multidish.jsonl  # strict and adjusted pass rates
```

The `v3-meal-day-week` episodes carry no `meal_composition`, so their strict and adjusted pass rates are empty;
the main pass rates are read on `v2-multidish`.

Each output is JSONL, one record per case and repeat, with a `.report.json` beside it. Its records are what the
mapping review reads ([baseline-mapping-review](baseline-mapping-review/README.md)).

## Known limits

- The strong-rule arm does not read nutrition targets, and its cost order is per gram of the cheapest package,
  not whole packages; the scorer recomputes the real purchase.
- The RAG candidates are retrieved by similarity only and are not filtered by the household's limits.
- Whether `response.usage` includes the search content tokens is not stated on the pricing page; the trial
  compares the ledger with the project's usage page.
- Blocking GitHub's domains does not block mirrors, other forges or web archives.
- The pure-LLM arm's own runner (`pure_llm_baseline.py`) is not on the ledger: it still counts the spend of earlier
  runs into the same output (ADR-0086), so a new output of that arm takes a `--max-usd` set by hand to what is left.
