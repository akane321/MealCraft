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

Every generated report records the SHA-256 digest of its input dataset. A
dataset change therefore creates a new experimental condition and must be
reviewed explicitly.

These assets implement Evaluation Protocol v1. The stronger comparative v2
design is documented in `docs/design/comparative-evaluation-v2.md`; its future
packets, labels and reports must use new versioned paths rather than overwriting
the v1 conditions.

Do not put prompts copied from real users, API keys, private account data or
live FairPrice responses in this directory.

The orchestration datasets are explicitly **developer sets**. Their scope and
grounding results must not be presented as final held-out generalisation
evidence. A separately authored and frozen holdout set is still required before
the final comparative evaluation. The grounding cases start from typed atomic
claims and therefore do not evaluate natural-language claim extraction.
