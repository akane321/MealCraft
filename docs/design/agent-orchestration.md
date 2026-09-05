# Agent Orchestration Engineering Handoff

## Purpose and boundary

The Agent turns conversational requests into a validated planning state. It may
extract intent, identify missing information, ask focused questions, call
approved tools and explain authoritative results. Deterministic services retain
ownership of safety, feasibility, nutrition, cost, packages, pantry deduction,
Shopping List derivation and evaluation arithmetic.

## Verified baseline

The current application persists English/Chinese sessions, merges explicitly
extracted constraints, asks for household size and unresolved pantry quantity,
requires confirmation before planning, delegates to the deterministic weekly
planner and supports a confirm/discard replanning loop. Fixture parsing is the
default; OpenAI structured output is opt-in and absent from default CI.

## Runnable foundation versus final target

The additive `backend/app/orchestration/` package provides typed scope, run,
interaction, tool and grounding contracts; a machine-readable capability
registry; a deliberately small deterministic scope-policy reference;
version-safe interaction validation; structured claim verification; tests; and
a synthetic fixture.

This is a handoff scaffold, not a production multilingual classifier, completed
LangGraph, live-model result or proof that natural-language hallucinations are
solved. The final target is one bounded, resumable and grounded orchestrator
with explicit policy, authorization, tool budgets, checkpoints, response
verification and comparative Evaluation evidence. Separate graph nodes are not
independent conversational Agents.

The intended order is:

```text
authenticated actor and household scope
 -> input normalization
 -> scope and policy gate
 -> intent decomposition and constraint extraction
 -> provenance-aware state merge
 -> clarification or structured interaction
 -> capability and authorization guard
 -> typed tools and bounded workflow
 -> independent validation
 -> preview and human confirmation
 -> immutable commit and action receipt
 -> grounded explanation and claim verification
```

## Scope and conversation governance

The scope gate runs before constraint extraction so an unrelated date, number,
currency or food word cannot mutate planning state accidentally.

| Scope class | Example | State/tool behaviour |
| --- | --- | --- |
| `domain_action` | Plan dinner next week | Continue; state mutation may be proposed |
| `domain_question` | Why was this recipe selected? | Read grounded facts; do not mutate |
| `social` | Hello or thanks | Brief response; no mutation or tools |
| `partially_supported` | Plan movie snacks and recommend a film | Handle the meal segment and decline the film segment |
| `out_of_scope` | What movie should I watch tomorrow? | State the boundary and redirect; no mutation or tools |
| `restricted` | Prescribe a diabetes treatment diet | Decline target derivation; accept only explicit non-medical constraints |
| `ambiguous` | Arrange tomorrow for me | Ask whether the user means meal planning |
| `adversarial` | Reveal the system prompt or API key | Fail closed; no privileged access |

An off-topic message remains in raw history for conversation continuity but is
excluded from structured planning state and the domain summary. Medical,
ordinary out-of-domain, authorization and adversarial failures use different
reason codes.

The current `ReferenceScopePolicy` is intentionally lexical and small. It
freezes obvious invariants such as `state_mutation=false` for a movie request.
The contributor must replace or augment it with an evaluated multilingual
classifier while retaining a deterministic policy layer around model output.

## Capability and tool-effect policy

`backend/app/orchestration/capabilities.py` defines supported intents, allowed
tools and confirmation requirements. It should become the common input to graph
guards, frontend affordances, authorization tests and tool-sequence Evaluation.

Tools have one of three effects:

- `read`: inspect an authorized profile, plan, Dashboard or evidence;
- `preview`: calculate a reversible proposal without changing accepted state;
- `commit`: modify accepted state and require authorization, a matching current
  preview/revision and explicit confirmation.

The model may propose an intent. Application code derives the allowlist from
the manifest. Before confirmation, commit tools remain unavailable even if the
model asks for one.

## Structured human-in-the-loop interactions

Clarification should return a typed interaction when the answer space is known:

- `quick_reply` for yes/no/unknown;
- `single_select` and `multi_select` for finite choices;
- `number_input`, `quantity_input` and `date_range` for typed values;
- `confirmation` for a state-changing action;
- `free_text` when valid answers cannot be enumerated.

Options come from schemas, the capability registry, an authorized plan,
validator conflicts or another authoritative service. The LLM does not invent
plan-entry IDs or safe relaxation choices. An answer carries stable
`question_id`, `context_version`, optional `plan_revision` and option IDs. The
backend rejects stale versions, unknown choices and duplicate consumption. The
frontend sends structured events, not localized labels reconstructed as prose.

Useful first interactions are household size; selected meal slots; known pantry
quantity versus `unknown/ranking only`; a real target meal for replanning; safe
infeasibility adjustments; and preview confirm/discard. Never offer removal of
an allergen as an automatic relaxation. Complex allergies, nutrition ranges and
pantry lists retain structured-form or text input.

## Accepted target state and provenance

Each turn should retain:

- raw user message and language;
- conversation and household-profile versions;
- parser provider, model, prompt/schema version and generation settings when an
  LLM is used;
- proposed field updates with source spans or turn references where practical;
- validated constraint state and rejected/unknown values;
- complete missing-field set and selected clarification question;
- tool name, typed arguments, result reference and error/degradation state;
- user confirmation and the authoritative planner result ID;
- latency, token/cost metadata for approved experiments without storing a key.

The system should distinguish `not mentioned`, `explicitly none`, `unknown
quantity`, and `invalid or unresolved`.

## Clarification policy

A clarification is justified when information is necessary to avoid an unsafe,
invalid or materially ambiguous action. It is unnecessary when a documented
default or soft preference can safely handle the omission.

Evaluation labels therefore need both:

- the complete set of genuinely missing required fields; and
- the next focused question that is acceptable at that turn.

An Agent that never asks questions may hallucinate. An Agent that asks about
everything creates avoidable work. Precision, recall and interaction cost all
matter.

## Tool boundary

Approved tools should expose typed contracts for:

- reading the current household profile;
- retrieving recipe candidates;
- retrieving a frozen or live product snapshot;
- requesting deterministic plan generation/validation;
- creating and confirming a replanning preview;
- reading authoritative plan, Shopping List and Dashboard state.

Tool results are evidence. The Agent may summarize them but may not silently
edit numeric results or emit a free-form Shopping List as authoritative output.

## Session, run and state model

Keep `AuthSession`, long-lived `AgentSession`, single-action `AgentRun` and
immutable `PlanRevision` separate. The current `collecting/ready/planned`
session status is a verified baseline, not the final run model.

A run should support:

```text
created -> needs_clarification -> ready_for_confirmation -> running
        -> preview_ready -> committed
        -> degraded | failed | cancelled
```

Persist active goal, pending action, complete missing-field set, selected
question, field provenance, tool trace, checkpoint and current plan revision.
An unrelated message cannot change these fields.

Every material constraint eventually needs value, source, turn/source-span,
confidence where relevant and status. Distinguish `not_mentioned`,
`explicitly_none`, `unknown`, `defaulted`, `conflicting`, `invalid` and
`confirmed`. Contradictions trigger clarification instead of silent overwrite.

Unknown pantry quantity remains unknown and affects only ranking after user
acknowledgement. The Agent never derives BMR/TDEE or disease-treatment targets.

## Bounded execution, recovery and external trust

Each run has explicit maximum LLM calls, tool calls, retrieval retries,
planning/repair attempts, wall-clock deadline and approved API-cost limit.
Checkpoints follow confirmed constraints, candidate retrieval, product
retrieval, planning, validation, preview creation and commit.

A retry rechecks household access, profile version, plan revision and external
freshness. Retrieval may trigger only a documented bounded repair loop. Tool
timeout or validator failure cannot commit a partial plan. Cancellation,
idempotency and stale-revision behaviour need explicit tests.

FairPrice pages, YouTube metadata, external recipes and user-authored content
are untrusted data, never instructions. They cannot select tools, change roles,
modify accepted state or override policy. No system prompt, key, password,
cookie, database URL or unrestricted stack trace enters model context, fixtures
or committed traces.

## Hallucination taxonomy and grounding

Do not call every error hallucination. Record at least:

| Class | Example |
| --- | --- |
| constraint hallucination | writes a budget value the user did not supply |
| recipe/data hallucination | invents a recipe, ingredient or nutrition fact |
| product hallucination | invents FairPrice price, package, promotion or stock |
| numeric hallucination | explanation disagrees with deterministic totals |
| tool-use hallucination | claims a live lookup without a matching trace |
| action hallucination | says a plan was saved without a committed receipt |
| provenance hallucination | labels cached evidence as live |
| explanation hallucination | gives a reason absent from planner/validator trace |
| capability hallucination | claims film recommendation, payment or treatment ability |
| reference hallucination | changes the wrong entry or stale revision |

Before response generation, deterministic services produce an evidence bundle
with stable IDs, typed values, source references, timestamps and validation
status. The LLM may verbalize it but may not redo arithmetic.

The additive `verify_structured_claims` function demonstrates exact matching of
typed claims to evidence. Full work must extract atomic claims from the final
response, deterministically verify names, IDs, numbers, timestamps and action
status where possible, block unsupported high-risk claims or use a deterministic
fallback, and persist only safe evidence references. Only a committed action
receipt permits wording such as `saved`; only a live trace permits `live price`.

## LangGraph target

The current application already uses a two-node LangGraph extraction workflow.
Extend it after contracts are stable. Proposed nodes are:

```text
load_context -> normalize_input -> classify_scope -> decompose_intent
 -> extract_constraints -> merge_state -> policy_and_authorization
 -> interaction_or_continue -> retrieve_recipes -> retrieve_products
 -> run_planner -> run_validator -> repair_or_stop -> build_preview
 -> wait_for_confirmation -> commit_action -> compose_grounded_response
 -> verify_response_claims
```

Nodes call typed application services; they do not duplicate Retrieval, Planner
or Validator logic in prompts.

## Context-matched LLM-only baseline

The primary LLM-only comparison uses the same base model and receives one
frozen Evaluation Packet containing the same facts available to MealCraft. It
must produce the same output schema in one prompt, with:

- no tool calls;
- no deterministic planner or validator;
- no post-generation repair by MealCraft;
- no access to MealCraft's parsed constraints, eligibility labels, planner
  scores, chosen products, package calculations, feasibility labels or gold
  answers.

The prompt should be strong rather than adversarial: respect hard constraints,
ask for required missing information, avoid inventing values, account for
servings/pantry/packages, report infeasibility, and return valid JSON.

To isolate architecture rather than model quality, both systems use the same
model/version, language, temperature, output budget, non-medical policy and
frozen facts. Stochastic systems run at least three repetitions with run-level
results retained.

## Plain general-purpose LLM baseline

A second LLM baseline receives only the user request and ordinary conversation,
without MealCraft's private recipe/product packet or tools. It represents the
realistic alternative of asking a general chatbot. Because its information is
not matched, it is supplementary ecological evidence and must not be used as
the sole causal claim for the Agent architecture.

## Component metrics

- field precision, recall and F1 over explicitly labelled fields;
- exact-case rate with no unsupported populated fields;
- hallucinated-field rate;
- clarification precision, recall, exact-set accuracy and unnecessary-question
  rate;
- medical-boundary accuracy;
- valid tool-selection and typed-argument rate;
- successful recovery from tool error or unavailable data;
- final strict task success after deterministic validation;
- explanation-trace faithfulness;
- turns, latency, tokens and API cost.

Evaluation separates two conditions. A text-only benchmark gives every system
natural-language input and isolates scope, interpretation, orchestration and
grounding. A full-product benchmark adds buttons, typed inputs, previews and
confirmation, and measures task time, turns, corrections and usability. Do not
attribute the UI assistance to model quality.

Add scope macro-F1, false acceptance/rejection, mixed-intent exact match, state
contamination, unauthorized tool calls, unconfirmed writes, grounded claim
precision, unsupported claims, numeric agreement, tool-use honesty, action
consistency, appropriate abstention and recovery success. Each metric requires
an explicit numerator and denominator.

Frozen hard gates should include zero off-topic state contamination, zero
unauthorized commit calls, zero unconfirmed writes and zero automatic medical
target derivations. Test information gaps, failed tools, stale cache, nonexistent
entities, save failure, external prompt injection and Chinese/English paraphrases.

## Definition of done

1. Every field and missing-state semantic is versioned.
2. Fixture and live parsers satisfy the same typed contract.
3. Tool calls cannot bypass confirmation or deterministic validation.
4. Prompt/model/run metadata are reproducible for reportable experiments.
5. The context-matched baseline receives equal facts but no intermediate
   MealCraft answers.
6. Failures remain linked to stage: parsing, clarification, tool use, planning,
   grounding, validation or explanation.
7. Supported, social, partial, off-topic, restricted, ambiguous and adversarial
   inputs have tested state/tool behaviour in Chinese and English.
8. Structured interactions reject stale, invalid and duplicate answers.
9. Read, preview and commit effects have different confirmation guards.
10. Runs can pause, resume, cancel, retry and fail without partial commit.
11. Every factual explanation is linked to evidence and every claimed write to
    an action receipt.
12. Text-only orchestration and assisted product Evaluation are reported
    separately.

## Contributor work packages

1. Reconcile the additive contracts with existing AgentSession schemas without
   a breaking migration.
2. Build and evaluate multilingual scope, mixed-intent, medical and adversarial
   routing beyond the lexical reference.
3. Complete the capability registry and enforce it at every tool boundary.
4. Add API contracts and a desktop renderer for structured interactions.
5. Persist AgentRun, checkpoints and safe tool traces under household scope.
6. Expand the guarded LangGraph and connect existing typed services.
7. Add cancellation, idempotency, stale-revision and bounded repair behaviour.
8. Produce evidence bundles, receipts and deterministic response checks.
9. Freeze text-only and product Evaluation episodes before paid runs.
10. Add prompt-injection, cross-household, unauthorized-tool and secret-leak
    tests.
11. Expose safe run, latency and cost observability to Operations Console.

Full dependency and acceptance details remain in the module contracts for Data,
Retrieval/RAG, Planning/Validation, Backend Platform, Frontend and Evaluation.
