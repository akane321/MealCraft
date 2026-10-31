# External recipe intake manual spot-check

Status: **PAUSED — 0/30 samples scored.** Du Jiayu reports owner approval to proceed on 2026-10-26. The owner has since run one separate product-code diagnostic with the same key and `gpt-5.4-mini`: the owner reports OpenAI returned in 10.6 seconds, hosted web search ran twice, and the response cited the matching recipe page (`resp_0a379fdd645ce16b006ae0258cde7c87d0bd3a0cc0c0bda494`). The extraction was rejected by local validation because `servings_basis`/`time_basis` were source prose and `course`/`cuisine` were arrays. This owner-reported diagnostic is outside the frozen 30-item sample, has no raw response in this audit bundle, and is not scored evidence. The owner also reports October project spend of approximately $1.35; this is a dashboard-level approximate amount, not a per-attempt audit cost reconciliation. The three earlier local calls remain unpriced individually: the first ER-01 response/usage was lost when D: was full, and the ER-01 retry plus ER-02 returned HTTP 503 `provider_unavailable` with no usage record. Keep the 30-item audit paused until the requested code fixes are reviewed/merged and the run-level spend can be checked.

## Frozen sampling plan

- Candidate frame: `candidate-frame.json` (53 URLs surfaced by predeclared English/Chinese local-dish and ordinary recipe-site searches; each recipe page is listed once).
- Sample: `sample.json`, fixed seed `20261025`, stratified selection without replacement: 8 English Singapore/Malaysia, 8 Chinese Singapore/Malaysia, 7 ordinary English, 7 ordinary Chinese.
- The frame is a convenience frame, not a probability sample of all public recipes. Results must not be generalized beyond this frame.
- `review-template.csv` now records each exact source URL as the planned extraction query. Do not replace failed samples after seeing model output; report unusable extraction as a failure for extraction/citation fields and record the reason.

## Per-recipe scoring

Use `review-template.csv`. Independently compare the extracted recipe against the cited source for: complete ingredient lines; quantities and units; standard ingredient mapping; allergen derivation; dish role; source/citation; and admit/reject decision with reason. Record safety-critical errors separately. The implementation author is also the reviewer; no second reviewer has been assigned.

## Results

| Measure | Result |
|---|---|
| Scored / planned | 0 / 30 |
| Intake attempts with recoverable evidence | 0/3 local attempts; one owner diagnostic is reported separately and is outside the sample |
| Ingredient lines complete | Pending |
| Quantities and units correct | Pending |
| Canonical ingredient mappings correct | Pending |
| Allergen decisions correct | Pending |
| Dish roles correct | Pending |
| Source/citation correct | Pending |
| Admission decisions and reasons correct | Pending |
| Safety-critical errors | Pending |
| Wilson 95% confidence intervals | Pending |
| Cumulative audit spend | Per-attempt audit cost unknown; owner reports October project spend of approximately $1.35; scored sample spend is $0.00 |

No accuracy claim is made before the audit is run. Any safety-critical error blocks a pass; repair and a fresh, separately sampled batch are required before reporting final accuracy.

## Bounded call setup

- The API key in the ignored local `.env` completed a small Responses API connectivity check on 2026-10-26: `gpt-5.4-mini`, 13 input tokens, 5 output tokens, no web-search call. This was not a recipe extraction and is outside the 30-sample denominator.
- The earlier 2026-10-25 pilot with the prior shell key returned `429 insufficient_quota` before processing. Do not count it as a recipe result.
- Local code changes now set `max_output_tokens=3000` for the external search route and retain per-call input/output token and web-search-call counts in the Operations trace. Targeted tests passed locally before the live attempt. These changes are uncommitted; only the route-level TestClient attempt described below has exercised the patched route, and that attempt's output was not retained.
- The Docker engine is currently unreachable (`docker info` cannot connect to the Docker Desktop Linux-engine pipe), so the persistent local stack cannot yet run end-to-end. The in-memory TestClient route was used for the single unscorable ER-01 attempt below.
- On 2026-10-26, ER-01's first request went through the FastAPI `/api/external-recipes/search-and-intake` route using TestClient and an in-memory SQLite catalog. The route returned to the harness, but writing the captured response/trace failed with `No space left on device` because D: was full. HTTP status, extraction, citation, admission result, and token/search usage were not retained. It is unscorable, with unknown outcome and cost.
- After D: space was restored, ER-01 was attempted again once. This attempt returned HTTP 503 `provider_unavailable`; the Operations trace records `api_usage: null`, and no recipe extraction or citation was produced. Its charge status is unknown. Both attempts are in `results.jsonl`; neither is included as a scored recipe. Do not retry ER-01 or call another sample until Platform Usage/Logs or the Owner resolves the unpriced spend and provider failure.
- ER-02 was then attempted once, following Du Jiayu's instruction to continue. It also returned HTTP 503 `provider_unavailable` with `api_usage: null`; no recipe extraction or citation was produced. It is recorded in `results.jsonl` and not scored. A non-billable `GET /v1/models` check succeeded and confirmed the project key can list the configured model; this does not verify Responses web search availability.
- Du Jiayu reports that the Owner agreed to enable log access. On the next check, the authenticated Platform `/logs` page still showed the organization-level access restriction. Owner agreement is recorded, but the setting is not yet active for this account.
- On 2026-10-27, the Owner reported a separate successful product-code diagnostic (same key, model `gpt-5.4-mini`, no retries): 10.6 seconds, two hosted web-search calls, and a matching cited page. The model output did not satisfy the app's extraction contract (`servings_basis`/`time_basis` were prose and `course`/`cuisine` were arrays), so validation rejected it. The Owner supplied a Responses ID for later log lookup, but no raw response or per-call usage was added to this report. It is not one of the 30 frozen samples and does not count as a score.
- The Owner requested three code changes before continuing the audit: Responses `text.format` strict JSON Schema output matching `ExtractedRecipe`; preserve exception class/status/code/message/request ID in logs and intake traces while mapping timeouts to 504 and upstream 4xx to 502; and set the external recipe OpenAI client to `max_retries=0`. These fixes are being prepared for review; they are not merged yet.
- The temporary 50 MB virtual environment created on D: for this attempt was moved to the Windows temp directory on C:; D: had about 50 MB free afterward. Recheck available space before writing large artifacts. The Docker engine remains unavailable, but this TestClient attempt shows that a route-level run does not require Docker; it does not prove persistent-stack behavior.
- For any resumed run, continue sequentially, one recipe per request, no automatic retries. Write each response and usage to a durable location before moving on; stop before another request if cumulative estimated spend approaches the approved $5.00 cap or if usage is absent/unpriceable. The last two attempts met the stop condition; provider diagnosis and cost reconciliation are required before resuming.

The smoke check and code-level tests are setup evidence only; they do not count as external-recipe extraction or human scoring.
