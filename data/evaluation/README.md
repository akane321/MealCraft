# Evaluation datasets

MealCraft separates data used during implementation from data used to report
generalisation performance.

| Dataset | Version | Exposure rule | Purpose |
|---|---|---|---|
| `dev/planning-v1.json` | v1 | May be inspected and used while developing | CI quality gate and regression detection |
| `heldout/planning-v1.json` | v1 | Do not tune planner weights or thresholds against its results | Baseline comparison and category reporting |
| `agent/fixture-v1.json` | v1 | May be extended, but existing expected values are immutable | Offline constraint extraction and clarification benchmark |

Every generated report records the SHA-256 digest of its input dataset. A
dataset change therefore creates a new experimental condition and must be
reviewed explicitly.

These assets implement Evaluation Protocol v1. The stronger comparative v2
design is documented in `docs/design/comparative-evaluation-v2.md`; its future
packets, labels and reports must use new versioned paths rather than overwriting
the v1 conditions.

Do not put prompts copied from real users, API keys, private account data or
live FairPrice responses in this directory.
