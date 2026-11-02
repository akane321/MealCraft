"""Data release v3, step 2: enrich the selected recipes with the OpenAI API (amends ADR-0030's choice of sessions).

    python scripts/enrich_v3_openai.py [--limit 5] [--ids ID ...] [--max-usd 25] [--workers 6]

Reads `data/staging/v3_selected.jsonl` (`select_v3_candidates.py`) and enriches each recipe with the same fields,
vocabulary and instructions as the v2 recipe packets (`enrichment-work/README.md`, section "Recipe items"). The input of
a recipe is built by `prepare_v2_inputs.recipe_item`, the answer must satisfy `v2_packet.check_recipe`; a rejected
answer is asked again once with the reasons, then recorded as failed. Estimated times, servings and line amounts carry
their evidence and confidence as in v2 (ADR-0076).

Appends to `data/staging/v3_merged.recipes.jsonl` (the shape of `v2_merged.recipes.jsonl`, `enriched_by`
"openai/<model>"), `v3_enrich_failed.jsonl` and `v3_enrich_usage.jsonl` (tokens and US dollars of
every call), and refreshes the committed `data/enrichment/v3_enrichment_summary.json`. Nothing is overwritten
and finished recipes are skipped, so re-running the same command resumes. The run stops when the returned usage
would pass `--max-usd` or after repeated API errors.

The key is read from the OPENAI_API_KEY environment variable, else from that one line of `--env-file`. It is never
printed or written.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import v2_packet  # noqa: E402
from prepare_v2_inputs import read_jsonl, recipe_item  # noqa: E402

STAGING = ROOT / "data" / "staging"
SELECTED = STAGING / "v3_selected.jsonl"
MERGED = STAGING / "v3_merged.recipes.jsonl"
FAILED = STAGING / "v3_enrich_failed.jsonl"
USAGE = STAGING / "v3_enrich_usage.jsonl"
SUMMARY = ROOT / "data" / "enrichment" / "v3_enrichment_summary.json"
README = ROOT / "enrichment-work" / "README.md"
DEFAULT_ENV = ROOT.parent / ".env"
URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.4-mini"  # backend/app/core/config.py openai_model
# USD per million tokens (input, cached input, output): backend/app/orchestration/model_pricing.py, checked 2026-10-21.
RATES = {"gpt-5.4-mini": (0.75, 0.075, 4.50)}
MAX_OUTPUT_TOKENS = 4000
STOP_AFTER_API_ERRORS = 8  # in a row
API_ATTEMPTS = 3
BACKOFF_SECONDS = (2.0, 8.0)
VOCAB = v2_packet.VOCAB
FIELDS = ("time", "servings", "course", "cuisine", "meal_types", "difficulty")

PREFACE = """You enrich recipes for MealCraft, a weekly meal planner for households in Singapore. You get one recipe
and answer with the JSON object of the supplied schema, which holds the fields described below. The candidate_id is
added for you. Use only the recipe itself, and no tools. Write `consumed_estimates` as an empty list when none
applies and `line_estimates` as an empty list when no line needs an amount. Leave `exclude_reason` empty unless the
item is not food at all, in which case give the reason (at least 10 characters) there and fill the other fields with
any valid values; they are ignored.

The rules follow, from the instruction sheet of the release v2 enrichment.
"""


@lru_cache
def instructions() -> str:
    """The recipe rules of `enrichment-work/README.md`, word for word, after a short preface."""
    text = README.read_text(encoding="utf-8")
    recipe_rules = text[text.index("### Recipe items") : text.index("### Do not")]
    donts = [
        line
        for line in text[text.index("### Do not") :].splitlines()[1:]
        if line.startswith("- ") and "source URL" not in line and "allergen label" not in line
    ]
    return PREFACE + "\n" + recipe_rules.strip() + "\n\n### Do not\n\n" + "\n".join(donts) + "\n"


def estimate_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["index", "quantity", "unit", "basis"],
        "properties": {
            "index": {"type": "integer"},
            "quantity": {"type": "number"},
            "unit": {"type": "string", "enum": sorted(v2_packet.ESTIMATE_UNITS)},
            "basis": {"type": "string"},
        },
    }


def response_schema() -> dict:
    """The strict JSON schema of an answer: the v2 recipe result without `candidate_id`, plus `exclude_reason`."""
    fields = {
        "exclude_reason": {"type": "string"},
        "prep_minutes": {"type": "integer"},
        "cook_minutes": {"type": "integer"},
        "passive_minutes": {"type": "integer"},
        "time_basis": {"type": "string", "enum": ["stated", "estimated"]},
        "servings": {"type": "integer"},
        "course": {"type": "string", "enum": VOCAB["course"]},
        "cuisine": {"type": "string", "enum": VOCAB["cuisine"]},
        "meal_types": {"type": "array", "items": {"type": "string", "enum": VOCAB["meal_types"]}},
        "difficulty": {"type": "string", "enum": VOCAB["difficulty"]},
        "line_estimates": {"type": "array", "items": estimate_schema()},
        "consumed_estimates": {"type": "array", "items": estimate_schema()},
        "evidence": {
            "type": "object",
            "additionalProperties": False,
            "required": list(FIELDS),
            "properties": {k: {"type": "string"} for k in FIELDS},
        },
        "confidence": {
            "type": "object",
            "additionalProperties": False,
            "required": list(FIELDS),
            "properties": {k: {"type": "number"} for k in FIELDS},
        },
    }
    return {"type": "object", "additionalProperties": False, "required": list(fields), "properties": fields}


def build_request(item: dict, model: str, effort: str | None, rejected: list[str] | None = None) -> dict:
    """The chat-completions request for one recipe item; `rejected` are the reasons the previous answer failed."""
    user = json.dumps(item, ensure_ascii=False)
    if rejected:
        user += "\n\nYour previous answer was rejected: " + "; ".join(rejected) + ". Answer again, fixing exactly that."
    request = {
        "model": model,
        "messages": [{"role": "system", "content": instructions()}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "recipe_enrichment", "strict": True, "schema": response_schema()},
        },
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
    }
    if effort:
        request["reasoning_effort"] = effort
    return request


def to_result(item: dict, answer: dict, model: str) -> dict:
    """The answer in the shape of a v2 packet result (`enriched_by` marks the model)."""
    reason = str(answer.get("exclude_reason") or "").strip()
    if reason:
        return {"candidate_id": item["candidate_id"], "exclude": reason, "enriched_by": f"openai/{model}"}
    result = {k: v for k, v in answer.items() if k != "exclude_reason"}
    if not result.get("consumed_estimates"):
        result.pop("consumed_estimates", None)
    return {"candidate_id": item["candidate_id"], **result, "enriched_by": f"openai/{model}"}


def cost_usd(usage: dict, model: str) -> float:
    rate_in, rate_cached, rate_out = RATES[model]
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    fresh = usage.get("prompt_tokens", 0) - cached
    return (fresh * rate_in + cached * rate_cached + usage.get("completion_tokens", 0) * rate_out) / 1_000_000


def load_api_key(env_file: Path) -> str:
    """OPENAI_API_KEY from the environment, else that one line of the env file; nothing else is read."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENAI_API_KEY":
                key = value.strip().strip("\"'")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set and not in the env file")
    return key


class ApiError(Exception):
    """The API did not answer after the retries (rate limit, timeout, server or request error)."""


def http_client(key: str, timeout: float = 120.0) -> Callable[[dict], dict]:
    def call(request: dict) -> dict:
        body = json.dumps(request).encode("utf-8")
        last = "no attempt"
        for attempt in range(API_ATTEMPTS):
            http = urllib.request.Request(
                URL, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(http, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:300]
                last = f"HTTP {error.code}: {detail}"
                if error.code not in {408, 409, 429} and error.code < 500:
                    raise ApiError(last) from None
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last = f"{type(error).__name__}: {error}"
            if attempt < API_ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS[attempt])
        raise ApiError(last)

    return call


def enrich_one(item: dict, client: Callable[[dict], dict], model: str, effort: str | None) -> dict:
    """Ask for one recipe, twice at most. Returns the result (or None), the calls' usage and the last errors."""
    calls, rejected = [], None
    for attempt in (1, 2):
        response = client(build_request(item, model, effort, rejected))
        usage = response.get("usage") or {}
        call = {
            "attempt": attempt,
            "usd": round(cost_usd(usage, model), 6),
            **{k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")},
        }
        call["cached_tokens"] = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        calls.append(call)
        choice = (response.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        try:
            answer = json.loads(content)
            if not isinstance(answer, dict):
                raise ValueError("not an object")
        except (TypeError, ValueError):
            rejected = [f"not a JSON object (finish_reason {choice.get('finish_reason')})"]
            call["status"] = "rejected"
            continue
        result = to_result(item, answer, model)
        errors = v2_packet.check_recipe(item, result)
        call["status"] = "rejected" if errors else "ok"
        if not errors:
            return {"result": result, "calls": calls, "errors": []}
        rejected = errors
    return {"result": None, "calls": calls, "errors": rejected}


class Budget:
    """Counts returned usage and reserves each call's worst case, so the cap is never passed."""

    def __init__(self, max_usd: float, spent: float, model: str) -> None:
        self.max_usd, self.spent, self.reserved, self.model = max_usd, spent, 0.0, model
        self.lock = threading.Lock()

    def worst_case(self, item: dict) -> float:
        rate_in, _, rate_out = RATES[self.model]
        prompt_tokens = (len(instructions()) + len(json.dumps(item))) / 3
        return 2 * (prompt_tokens * rate_in + MAX_OUTPUT_TOKENS * rate_out) / 1_000_000  # two attempts

    def reserve(self, amount: float) -> bool:
        with self.lock:
            if self.spent + self.reserved + amount > self.max_usd:
                return False
            self.reserved += amount
            return True

    def settle(self, reserved: float, actual: float) -> None:
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


def existing(path: Path) -> list[dict]:
    return read_jsonl(path) if path.exists() else []


def write_summary() -> dict:
    """What the staging logs say about the run so far, to the committed summary (the logs are git-ignored)."""
    results, failed, calls = existing(MERGED), existing(FAILED), existing(USAGE)
    done = {r["candidate_id"] for r in results}
    summary = {
        "model": sorted({r["enriched_by"] for r in results}),
        "selected": len(read_jsonl(SELECTED)),
        "enriched": len(done),
        "excluded_by_enricher": sum("exclude" in r for r in results),
        "failed_validation_twice": len({r["candidate_id"] for r in failed} - done),
        "calls": len(calls),
        "calls_rejected_by_validation": sum(c["status"] == "rejected" for c in calls),
        "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
        "cached_prompt_tokens": sum(c["cached_tokens"] for c in calls),
        "completion_tokens": sum(c["completion_tokens"] for c in calls),
        "usd_from_returned_usage": round(sum(c["usd"] for c in calls), 4),
        "rates_usd_per_million_tokens": dict(zip(("input", "cached_input", "output"), RATES[MODEL], strict=True)),
        "by_cuisine": dict(collections.Counter(r["cuisine"] for r in results if "exclude" not in r).most_common()),
        "by_course": dict(collections.Counter(r["course"] for r in results if "exclude" not in r).most_common()),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


def append(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def run(args: argparse.Namespace, client: Callable[[dict], dict]) -> int:
    records = read_jsonl(SELECTED)
    done = {r["candidate_id"] for r in existing(MERGED)}
    failed = {r["candidate_id"] for r in existing(FAILED)}
    todo = [
        record_item
        for record_item in map(recipe_item, records)
        if record_item["candidate_id"] not in done
        and (args.retry_failed or record_item["candidate_id"] not in failed)
        and (not args.ids or record_item["candidate_id"] in args.ids)
    ]
    todo = todo[: args.limit] if args.limit else todo
    spent = sum(call.get("usd", 0.0) for call in existing(USAGE))
    budget = Budget(args.max_usd, spent, args.model)
    print(
        f"{len(records)} selected, {len(done)} done, {len(failed)} failed; asking for {len(todo)}; "
        f"US${spent:.4f} spent so far of US${args.max_usd}"
    )
    counts = {"ok": 0, "failed": 0, "api_errors": 0}
    streak, stopped = 0, None
    pending: dict = {}
    queue = iter(todo)

    def handle(future, item, reserved) -> None:
        nonlocal streak, stopped
        try:
            outcome = future.result()
        except ApiError as error:
            budget.settle(reserved, 0.0)
            counts["api_errors"] += 1
            streak += 1
            print(f"{item['candidate_id']}: API error: {error}")
            if streak >= STOP_AFTER_API_ERRORS:
                stopped = f"{streak} API errors in a row"
            return
        streak = 0
        now = datetime.now(UTC).isoformat(timespec="seconds")
        usd = sum(call["usd"] for call in outcome["calls"])
        budget.settle(reserved, usd)
        append(
            USAGE,
            [{"candidate_id": item["candidate_id"], "model": args.model, "at": now, **c} for c in outcome["calls"]],
        )
        if outcome["result"] is not None:
            append(MERGED, [outcome["result"]])
            counts["ok"] += 1
        else:
            append(FAILED, [{"candidate_id": item["candidate_id"], "errors": outcome["errors"], "at": now}])
            counts["failed"] += 1
            print(f"{item['candidate_id']}: failed validation twice: {'; '.join(outcome['errors'])}")
        finished = counts["ok"] + counts["failed"]
        if finished % 100 == 0:
            print(f"{finished} finished, {counts['failed']} failed, US${budget.spent:.4f} spent", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while True:
            while len(pending) < args.workers and stopped is None:
                item = next(queue, None)
                if item is None:
                    break
                reserve = budget.worst_case(item)
                if not budget.reserve(reserve):
                    stopped = f"the next call could pass --max-usd {args.max_usd}"
                    break
                pending[pool.submit(enrich_one, item, client, args.model, args.reasoning_effort)] = (item, reserve)
            if not pending:
                break
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                item, reserve = pending.pop(future)
                handle(future, item, reserve)
    write_summary()
    print(f"done: {counts}; US${budget.spent:.4f} spent in total" + (f"; stopped: {stopped}" if stopped else ""))
    return 1 if stopped else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="enrich at most this many recipes in this run")
    parser.add_argument("--ids", nargs="+", help="only these candidate ids")
    parser.add_argument("--max-usd", type=float, default=25.0, help="hard cap on the cost counted from returned usage")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--model", default=MODEL, choices=sorted(RATES))
    parser.add_argument("--reasoning-effort", default="low", help="reasoning_effort of the request; '' omits it")
    parser.add_argument("--retry-failed", action="store_true", help="ask again for recipes recorded as failed")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9.-]+", args.model):
        raise SystemExit("bad model name")
    return run(args, http_client(load_api_key(args.env_file)))


if __name__ == "__main__":
    sys.exit(main())
