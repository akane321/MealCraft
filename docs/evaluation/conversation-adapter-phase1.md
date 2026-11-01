# Conversation adapter: synthetic phase one

This is apparatus development under ADR-0092, **not run admission, a formal
freeze, a scored evaluation or proof of product end-to-end readiness**. The
[sealed handoff procedure](sprint2-heldout-freeze.md) remains authoritative.

## Implemented boundary

`backend/app/evaluation/conversation_adapter.py` takes original user strings,
one global `RuntimeConfig`, and a system callback. It has no episode loader,
gold argument, category switch, scorer, provider or initial-household/plan seed.

- One required anchor date and `Asia/Singapore` produce a fixed noon. The same
  clock sentence is in every system's shared instructions. The in-process
  product clock is injected through a context-local seam and restored on errors;
  ordinary product clock behavior is unchanged outside that context.
- Each authored turn is delivered unchanged. A structured
  `awaiting_confirmation=true` with no clarification triggers exactly one
  `I confirm. Please proceed.` message. A repeated marker does not loop.
  Questions take precedence. Counts are retained per system.
- A later turn receives only its own system's earlier exchanges, including any
  automatic confirmation. Every case starts with empty history. There is no
  target-reference parsing, simulated answer to a question, or gold-derived state.
- One `UnifiedOutput` contains plan, clarification, refusal, answer and
  request-field slots. Slots coexist: a question or refusal does not erase an
  actual plan. All arms receive the same schema, not a category-selected schema.
- `normalize_product` reads an actual `AgentSessionResponse` and, if saved,
  that session's actual `WeeklyMealPlanResponse`. It preserves dates, roles,
  actual dish servings, exclusions, nutrition and shopping observations. It
  retains the explicit horizon even on dates without dishes, and keeps skip/lock
  state rather than silently treating every saved entry as a selected meal. It
  rejects a missing or substituted saved plan. Native constraint echoes are
  copied without inferring dictionary fields from answers or recipe names.

`meal_day_week_runner.py` is deliberately unchanged. Its `plan_request` reads
gold constraints, so reusing it to construct a new end-to-end request would
violate the input boundary. Its selected-pool database importer and frozen-ID
projection may be candidates for later reuse, after the loader and mapping
receive their own review; neither is needed for these synthetic tests.

## Pending registration and independent review

The shared template, JSON schema, marker mapping, fixed noon and confirmation
bytes are **drafts**. Their exact bytes must be registered and reviewed for
neutrality by someone who did not write them before formal use. Neither the
synthetic example date nor a readiness attestation is run admission.

This phase does not implement a product transport, model arm, one-shot arm
presentation, field-dictionary mapping, catalog ID matching, scoring, sealed file loading, freeze or admission. A change
preview that is linked and not yet applied counts as waiting for confirmation in `normalize_product`, like a
plan card (see [product-transport.md](product-transport.md)). A caller
must not silently use an existing runner that reads gold. The product currently
separates conversational replies from confirmation actions; this harness does
**not** call a product-only confirm endpoint or treat a fixed message as a hidden
button click. A common, independently reviewed transport remains a prerequisite.
Missing transport support must not be reported as a proven infeasible request.

The clock seam covers in-process calls in the active context. A future
transport using separate processes must explicitly receive the same global
configuration, rather than relying on ambient process time. Callbacks must be
fresh per case or correctly reset their own internal state; the harness itself
does not create a saved profile or choose a parser/provider.

## Synthetic verification

Tests use invented words and validated, invented product response objects; no
recipe release or real questions are loaded. They cover original message bytes,
one confirmation, question precedence, own-history multi-turn references,
cross-system/case separation, mutation protection, failure propagation, normalizer
observations, wrong-plan rejection, and clock restoration/context isolation.

From the repository root with backend dependencies installed:

```text
python -m pytest backend/tests/test_conversation_adapter.py backend/tests/test_clock.py -p no:cacheprovider --basetemp <new-temporary-directory>
python -m app.evaluation.conversation_adapter_demo --output <first.json>
python -m app.evaluation.conversation_adapter_demo --output <second.json>
```

Set `PYTHONPATH=backend` when running from the repository root. Full-suite local
verification follows the task's protected-data exclusions; the documentation
integrity checker is left to CI. Do not substitute workbench or a sealed runner
for these commands. The demo has no input-file argument and cannot load questions.

The generated [synthetic report](conversation-adapter/synthetic.json) records
the draft shared instructions and three invented conversations. It contains no
latency, capability-accuracy or formal-baseline claim. Repeated generation must
be byte-identical; timings and machine timestamps are deliberately absent.
