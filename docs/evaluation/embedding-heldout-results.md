# Embedding held-out results (run once, 2026-09-26)

The two held-out sets for ingredient proposals (ADR-0041) and swap requests (ADR-0042) were written by
Zhang Naiqian with ChatGPT assistance from the sealed packet (`scripts/build_embedding_heldout_packet.py`),
checked, and frozen before this run (`data/evaluation/agent/*-heldout.frozen.json` hold the digests and the
scoring rules). They were scored as submitted: the tuning session changed no label. Both sets are now spent.

## A. Ingredient proposals

Registered rule: the primary result counts only terms that are not in the developer set (19 of the 43
submitted terms were), the full set second. Terms with no acceptable id are listed, not scored.

| Terms | Ranking | first proposal acceptable | acceptable among the four offered |
| --- | --- | --- | --- |
| **unseen (21 scored)** | spelling | 9 | 11 |
| **unseen (21 scored)** | **embedding + other names (shipped)** | **13** | **15** |
| all (39 scored) | spelling | 22 | 25 |
| all (39 scored) | embedding + other names (shipped) | 27 | 32 |

On unseen terms the shipped ranking offers an acceptable ingredient for 15 of 21 (71%), against 11 (52%) by
spelling; on the developer set it was 56 of 62. **Every unseen miss is a Chinese term** (茄子, 西兰花, 糯米,
米粉, 生抽, 叁巴): English, Malay, regional and misspelt terms carried over; short Chinese words did not.

## B. Swap requests

Twenty-one requests, 30 seeded pools of 100 catalog mains each, 608 trials whose pool held a recipe the
request's catalog check accepts.

| Method | picked what was asked for |
| --- | --- |
| ignore the request (before ADR-0042) | 8% |
| shared words | 50% |
| similarity alone | 66% |
| **similarity + shared words (shipped)** | **69%** |

Down from 80% on the developer requests, and well above ignoring the request. The misses are again mostly
Chinese or abstract: 「帮我换成素食的，不要肉」 0 of 30, 「我想吃豆腐」 2 of 20, 「换个面食吧」 3 of 30; "something
vegan" 10 of 27 and "with lemon in the dish" 10 of 29. Concrete English requests (shrimp, Japanese, Korean,
Chinese food, rice, curry) were near the ceiling.

## What follows

Short Chinese words are the shared weakness: one or two characters embed poorly against English recipe and
ingredient text. A fix (Chinese names in the catalog's other names, or translating the request before
embedding) must be developed on new developer terms and measured on a new held-out set; these two are spent.
