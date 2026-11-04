"""The general-agent baseline arm: the model with web search and a calculator only (02-baselines.md; #396).

"通用 agent + 工具" (owner, 2026-11-03 on #396: option A): the model gets the shared instructions of every arm
(ADR-0092) and two generic tools, OpenAI's hosted web search and a calculator, and plans by itself. It gets none of
MealCraft's recipe catalog, prices, planner or validator, so the arm measures a general agent on its own.

Each dish must carry its own ingredient lines in grams, steps and time in `evidence`, or the shared layers cannot
score it (an invalid output, never an infeasible one).

The loop (OpenAI Responses API): each user turn may take up to `MAX_STEPS` model responses; a response that calls
the calculator gets the result and continues; the last allowed response has tools off and must answer. Web search
runs inside a response, at most `MAX_SEARCHES` per response (`max_tool_calls`).

Cost (ADR-0086; the arm's tool fees count against its US$5): before each response the arm's ledger
(`baseline_arms.LedgerBudget`) must cover its worst case, the rendered input plus `MAX_SEARCHES` blocks of
`SEARCH_BLOCK_TOKENS` search content plus `MAX_OUTPUT_TOKENS`, plus the search fees, and that worst case is
reserved. After it, the reported tokens are charged with `SEARCH_USD` for each search call made. Prices, from the
OpenAI pricing page (owner review on #427, 2026-11-04): the `web_search` tool costs US$10 per 1,000 calls for every
model, and its search content tokens are billed at the model's rates. The fixed 8,000-token block per call applies
only to gpt-4o-mini and gpt-4.1-mini, so `SEARCH_BLOCK_TOKENS` is only the reserve before a call; what is charged
after it is the reported usage. The dev trial checks the ledger against the project's usage page.

The public web holds this repository (and its evaluation cases), so web search leaves out GitHub's domains
(`blocked_domains`). The search queries and sources, each response's status and usage go into the case's trace.
"""

from __future__ import annotations

import ast
import json
import operator
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.evaluation import baseline_arms
from app.evaluation.conversation_adapter import Exchange, Responder, UnifiedOutput
from app.evaluation.pure_llm_baseline import MAX_ATTEMPTS, Usage, price_usd
from app.evaluation.rag_baseline import estimate_tokens, parse_output

SYSTEM_ID = "general-agent"
MAX_OUTPUT_TOKENS = 6000
# Owner review on #427: one response can search MAX_SEARCHES times, so three steps allow two rounds of tools
# (searches, then the calculator) and one forced answer.
MAX_STEPS = 3
MAX_SEARCHES = 2
SEARCH_USD = 0.010
SEARCH_BLOCK_TOKENS = 8000
CONFIGURATION = """Your registered configuration: two tools. web_search searches the public web (recipes, typical
supermarket prices in Singapore, nutrition). calculator evaluates an arithmetic expression. You have no recipe
database, grocery database or planner of the user's service.
For every dish give evidence.ingredients as a list of {"name": ..., "quantity_g": ...} (every ingredient, in grams,
for the dish's servings), evidence.steps and evidence.cooking_time_minutes. Give total_cost_sgd as your estimate
of the groceries for the whole plan. When you have finished using tools, answer with the JSON only."""
CALCULATOR = {
    "type": "function",
    "name": "calculator",
    "description": "Evaluate an arithmetic expression with + - * / ** and parentheses, e.g. '3*4.5 + 2'.",
    "parameters": {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
        "additionalProperties": False,
    },
    "strict": True,
}
WEB_SEARCH = {
    "type": "web_search",
    "search_context_size": "medium",
    "filters": {"blocked_domains": ["github.com", "githubusercontent.com"]},
}
INCLUDE = ["web_search_call.action.sources"]
JSON_REMINDER = "Your last answer was not valid JSON for the shared output schema. Answer with that JSON only."

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def calculate(expression: str) -> str:
    """Arithmetic only: numbers, + - * / **, unary signs and parentheses. Anything else is an error string."""

    def value(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](value(node.operand))
        raise ValueError("only arithmetic is allowed")

    try:
        if len(expression) > 500:
            raise ValueError("expression too long")
        result = value(ast.parse(expression, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as error:
        return f"error: {error}"
    return repr(round(result, 6))


def _payload(item: Any) -> dict:
    return item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(item)


def worst_case_usd(model: str, input_tokens: int, searches: int = MAX_SEARCHES) -> tuple[int, float]:
    tokens = input_tokens + searches * SEARCH_BLOCK_TOKENS
    return tokens, price_usd(model, Usage(tokens, MAX_OUTPUT_TOKENS)) + searches * SEARCH_USD


class Agent:
    """One case's loop over the Responses API; `client` is an OpenAI client or a test double."""

    def __init__(
        self,
        client: Any,
        budget: baseline_arms.LedgerBudget,
        trace: list[dict] | None = None,
        keep_raw: bool = False,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.budget = budget
        self.sleep = sleep
        self.tool_calls: list[dict] = trace if trace is not None else []
        self.keep_raw = keep_raw

    def _create(self, items: list, tools_on: bool) -> Any:
        rendered = json.dumps(items, ensure_ascii=False, default=str)
        searches_allowed = MAX_SEARCHES if tools_on else 0
        tokens = len(rendered) // 4 + 1 + searches_allowed * SEARCH_BLOCK_TOKENS
        arguments: dict[str, Any] = {
            "model": self.budget.model,
            "input": items,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "text": {"format": {"type": "json_object"}},
        }
        if tools_on:
            arguments |= {"tools": [WEB_SEARCH, CALCULATOR], "max_tool_calls": MAX_SEARCHES, "include": INCLUDE}
        response = self.budget.paid(
            lambda: self.client.responses.create(**arguments),
            tokens,
            MAX_OUTPUT_TOKENS,
            extra_usd=searches_allowed * SEARCH_USD,
        )
        usage = getattr(response, "usage", None)
        reported = Usage(int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0))
        cached = int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
        searches = sum(_payload(item).get("type") == "web_search_call" for item in response.output or [])
        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        incomplete = _payload(incomplete) if incomplete is not None else None
        self.budget.charge(
            reported if reported.total_tokens else Usage(tokens, MAX_OUTPUT_TOKENS),
            extra_usd=searches * SEARCH_USD,
            call="response",
            cached_tokens=cached,
            searches=searches,
        )
        step = {
            "tool": "response",
            "status": status,
            "incomplete_details": incomplete,
            "input_tokens": reported.input_tokens,
            "cached_tokens": cached,
            "output_tokens": reported.output_tokens,
            "searches": searches,
        }
        if self.keep_raw:
            step["raw"] = [_payload(item) for item in response.output or []]
        self.tool_calls.append(step)
        return response

    def answer(self, items: list) -> UnifiedOutput:
        errors: list[str] = []
        attempts = 0
        for step in range(MAX_STEPS):
            response = self._create(items, tools_on=step + 1 < MAX_STEPS)
            output = [_payload(item) for item in response.output or []]
            calls = [item for item in output if item.get("type") == "function_call"]
            for item in output:
                if item.get("type") == "web_search_call":
                    self.tool_calls.append({"tool": "web_search", "action": item.get("action")})
            if calls:
                items = items + output
                for call in calls:
                    expression = json.loads(call.get("arguments") or "{}").get("expression", "")
                    result = calculate(str(expression))
                    self.tool_calls.append({"tool": "calculator", "expression": expression, "result": result})
                    items.append({"type": "function_call_output", "call_id": call["call_id"], "output": result})
                continue
            try:
                return parse_output(getattr(response, "output_text", "") or "")
            except (ValidationError, ValueError) as error:
                errors.append(f"malformed: {error}")
                attempts += 1
                if attempts >= MAX_ATTEMPTS:
                    break
                items = items + output + [{"role": "user", "content": JSON_REMINDER}]
        raise ValueError("; ".join(errors) or "no answer within the step limit")


def input_items(instructions: str, own_history: tuple[Exchange, ...], message: str) -> list[dict]:
    items: list[dict] = [{"role": "system", "content": instructions + "\n\n" + CONFIGURATION}]
    for item in own_history:
        items.append({"role": "user", "content": item.message})
        items.append({"role": "assistant", "content": item.output.model_dump_json(exclude_defaults=True)})
    items.append({"role": "user", "content": message})
    return items


def make_responder(context: baseline_arms.ArmContext, *, sleep: Callable[[float], None] = time.sleep) -> Responder:
    if context.model is None or context.budget is None:
        raise RuntimeError("the general-agent arm needs a client and a budget (a live run)")
    agent = Agent(context.model, context.budget, context.trace, context.keep_raw, sleep)

    def respond(message: str, own_history: tuple[Exchange, ...], instructions: str) -> UnifiedOutput:
        return agent.answer(input_items(instructions, own_history, message))

    return respond


def estimate(turns: list[str], instructions: str, model: str) -> tuple[int, int, float]:
    """Worst case of one case without the network: every turn answered and confirmed, each with `MAX_STEPS`
    responses (the last without tools), every response at its worst case, the history growing by a full output."""
    base = estimate_tokens([("system", instructions + "\n\n" + CONFIGURATION)])
    calls = tokens = history = 0
    usd = 0.0
    for turn in turns:
        for _ in range(2):  # the turn and its possible confirmation
            grown = base + history + len(turn) // 4 + 1
            for step in range(MAX_STEPS):
                searches = MAX_SEARCHES if step + 1 < MAX_STEPS else 0
                step_tokens, step_usd = worst_case_usd(model, grown, searches)
                calls += 1
                tokens += step_tokens
                usd += step_usd
                grown += searches * SEARCH_BLOCK_TOKENS + MAX_OUTPUT_TOKENS
            history += MAX_OUTPUT_TOKENS + len(turn) // 4 + 1
    return calls, tokens, usd


def create_client(model_name: str) -> Any:
    from openai import OpenAI

    from app.agent import model_client
    from app.core.config import get_settings

    settings = get_settings()
    if settings.openai_api_key is None:
        raise RuntimeError("a live run needs OPENAI_API_KEY at run time (tests inject a fake client)")
    return OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=max(settings.openai_timeout_seconds, 120),
        max_retries=2,
        http_client=model_client.http_client(),
    )


def fingerprint() -> dict[str, str]:
    return {
        "system_id": SYSTEM_ID,
        "configuration_sha256": baseline_arms.sha256_text(
            CONFIGURATION
            + json.dumps(
                {
                    "tools": [WEB_SEARCH, CALCULATOR],
                    "include": INCLUDE,
                    "max_steps": MAX_STEPS,
                    "max_searches": MAX_SEARCHES,
                },
                sort_keys=True,
            )
        ),
        "runner_sha256": baseline_arms.source_sha256(__file__),
    }


ARM = baseline_arms.Arm(
    system_id=SYSTEM_ID,
    paid=True,
    fingerprint=fingerprint,
    responder=make_responder,
    estimate=estimate,
    model_factory=create_client,
)
