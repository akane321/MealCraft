# Agent Orchestration Contract

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

## Definition of done

1. Every field and missing-state semantic is versioned.
2. Fixture and live parsers satisfy the same typed contract.
3. Tool calls cannot bypass confirmation or deterministic validation.
4. Prompt/model/run metadata are reproducible for reportable experiments.
5. The context-matched baseline receives equal facts but no intermediate
   MealCraft answers.
6. Failures remain linked to stage: parsing, clarification, tool use, planning,
   grounding, validation or explanation.
