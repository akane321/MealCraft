# Evaluation datasets

MealCraft separates data used during implementation from data used to report
generalisation performance.

| Dataset | Version | Exposure rule | Purpose |
|---|---|---|---|
| `dev/planning-v1.json` | v1 | May be inspected and used while developing | CI quality gate and regression detection |
| `heldout/planning-v1.json` | v1 | Do not tune planner weights or thresholds against its results | Baseline comparison and category reporting |
| `agent/fixture-v1.json` | v1 | May be extended, but existing expected values are immutable | Offline constraint extraction and clarification benchmark |
| `agent-orchestration/scope-developer-v1.json` | v1 | May be inspected and used while developing | Bilingual scope classification and state-isolation diagnostics |
| `agent-orchestration/grounding-developer-v1.json` | v1 | May be inspected and used while developing | Typed numeric, provenance, action and explanation-claim verification |
| `v2/dev/packet-source-v1.json` | v1 | May be inspected and changed with review | Neutral scenario references used to compile matched-information packets |
| `v2/dev/packets-v1.json` | dev-1 | Generated; do not edit by hand | Frozen, digest-protected facts for Rule-only, MealCraft and Context-matched LLM-only development runs |

Every generated report records the SHA-256 digest of its input dataset. A
dataset change therefore creates a new experimental condition and must be
reviewed explicitly.

These assets implement Evaluation Protocol v1. The stronger comparative v2
design is documented in `docs/design/comparative-evaluation-v2.md`; its future
packets, labels and reports must use new versioned paths rather than overwriting
the v1 conditions.

Do not put prompts copied from real users, API keys, private account data or
live FairPrice responses in this directory.

The orchestration and v2 packet datasets are explicitly **developer sets**. Their scope and
grounding results must not be presented as final held-out generalisation
evidence. A separately authored and frozen holdout set is still required before
the final comparative evaluation. The grounding cases start from typed atomic
claims and therefore do not evaluate natural-language claim extraction.

Compile the v2 developer packet bundle offline from the reviewed source files:

```bash
uv run --project backend --no-sync python -m app.evaluation.v2_packets
```

The compiler rejects unknown recipe/product IDs and rejects a FairPrice snapshot
unless it covers every normalized ingredient in the declared candidate pool.
The generated bundle records source and packet-set SHA-256 digests and always
sets `live_api_used` to `false`. It contains no model response, selected plan,
eligibility label, planner score, grocery total or gold answer.
