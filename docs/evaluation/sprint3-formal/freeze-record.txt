# Sprint 3 formal evaluation: freeze record

Computed by `python -m app.evaluation.formal_run --freeze-record` on 2026-11-06 17:25 UTC; not hand-written. Before the held-out run compare it with a fresh one: all but the date and the code commit must match, and `git diff` from that commit to HEAD must show only this record.

- Code commit: `b753843415f6fb01633c7701352065e235d1e252`
- Anchor date: 2026-10-23
- Release: v3, digest `af588d9f3134c21b3e45c7e21bc13787cbd714d18283eb445d5b1e4c72529f8c`
- Data tree: `d7f81da30b8dc08dd1227c159e2c0b7a04889a7e`; release tree: `058560ad2fd122783cd1b7c4796020eada5ec12e`
- `data-engineering/data/release/v3/ingredients.jsonl`: `4c71b1a9f13e738d7c82d8a302ef11543d0d1705b614d3dc05150b86529eb95e`
- `data-engineering/data/release/v3/release_manifest.json`: `1a4b9c9fbde2423369a2f798dd43e2f381dc05a2ad29fc3a74cbd64beac807d4`
- `data/products/fairprice-v2-snapshot.json`: `2cfd10e150fd38cb448cbd1da2eff9f2f59369c202dce18648dc119f4f1beb91`
- `data/ingredients/ingredients.json`: `c995508b5d9dde109b62d0cf3d8fad2e9086a115eaee5bdc50a7a5937f573fe8`
- `data/ingredients/basic-seasonings-v2.json`: `c188e5deee5840ba39c6841b8ead1dd5c71f75288b5f0c3cc8b313d2afbfa9f8`
- Scoring: formal-outcome-v2
- Smallest published cell: 5
- Episodes digest: `85645a75f66e1ef8ac996ccd06b399a12b5679278689cd467f171cc397a264a2`

| Arm | Paid | Cap (US$) | Parser or model | Fingerprint SHA-256 |
| --- | --- | --- | --- | --- |
| strong-rule | False | - | rules, no model | `d6dca326db3cdded` |
| pure-llm | True | 7.0 | gpt-5.4-mini | `f2ddb9cff0277faf` |
| rag | True | 8.0 | gpt-5.4-mini | `6d29ec9fcd525d49` |
| general-agent | True | 20.0 | gpt-5.4-mini | `6502c4b03c9c719d` |
| mealcraft | True | 5.0 | openai parser, gpt-5.4-mini | `51d4ac311a3d8be4` |
| mealcraft/ablation/retrieval_off | True | 5.0 | openai parser, gpt-5.4-mini | `cbf3016d1166b0cb` |
| mealcraft/ablation/rule_only_parser | True | 5.0 | rule parser (switch), no parser call | `b122d226d7f240f4` |
| mealcraft/ablation/independent_validator_off | True | 5.0 | openai parser, gpt-5.4-mini | `b5a5c8918b950997` |
| mealcraft/ablation/repair_off | True | 5.0 | openai parser, gpt-5.4-mini | `f476926a00debd7d` |
| mealcraft/ablation/diversity_off | True | 5.0 | openai parser, gpt-5.4-mini | `6b039ec4b4c84894` |
| mealcraft/ablation/local_improvement_off | True | 5.0 | openai parser, gpt-5.4-mini | `5214761342a6f306` |

```json
{
  "general-agent": {
    "configuration_sha256": "87e851c43c060ebcc73b22fe084d087298cbc10f816b1d7c0cf0e54b06da33b3",
    "runner_sha256": "85db6f0993ac7dd161696f58ffc7a321dc955b2976171b4b35a3684f179c69dc",
    "system_id": "general-agent"
  },
  "mealcraft": {
    "ablation": null,
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft"
  },
  "mealcraft/ablation/diversity_off": {
    "ablation": "diversity_off",
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft/ablation/diversity_off"
  },
  "mealcraft/ablation/independent_validator_off": {
    "ablation": "independent_validator_off",
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft/ablation/independent_validator_off"
  },
  "mealcraft/ablation/local_improvement_off": {
    "ablation": "local_improvement_off",
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft/ablation/local_improvement_off"
  },
  "mealcraft/ablation/repair_off": {
    "ablation": "repair_off",
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft/ablation/repair_off"
  },
  "mealcraft/ablation/retrieval_off": {
    "ablation": "retrieval_off",
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft/ablation/retrieval_off"
  },
  "mealcraft/ablation/rule_only_parser": {
    "ablation": "rule_only_parser",
    "data_tree": "d7f81da30b8dc08dd1227c159e2c0b7a04889a7e",
    "parser_model": "gpt-5.4-mini",
    "parser_provider": "openai",
    "release_tree": "058560ad2fd122783cd1b7c4796020eada5ec12e",
    "runner_sha256": "192f55c7a265a2316baaa5e30ef7392d982cfb71e534a527c0a2bca3b8cdf4aa",
    "system_id": "mealcraft/ablation/rule_only_parser"
  },
  "pure-llm": {
    "call_loop_sha256": "981e317747005c82534150c6bcf2895a3745da90faa94796be92dd615270bb1e",
    "configuration_sha256": "a3d16515641f712596deabc1273f9f432343446d9c94192d637c161e532cbf0f",
    "runner_sha256": "6be0579cd7db26f5e69c18cb76373f649c0120e7c66ffd97aa29c5e76886faa8",
    "system_id": "pure-llm"
  },
  "rag": {
    "configuration_sha256": "e10b7a3c8e62158611febff76ba63731637df7fe5ad45643868beafebd086d51",
    "runner_sha256": "981e317747005c82534150c6bcf2895a3745da90faa94796be92dd615270bb1e",
    "system_id": "rag"
  },
  "strong-rule": {
    "runner_sha256": "10e9a359fad377d8b01db0fe664ac1dc0f41da1f8d939d58c76ccaa1cacc3535",
    "system_id": "strong-rule"
  }
}
```
