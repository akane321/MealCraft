from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import enrich_v3_openai as enrich  # noqa: E402
import v2_packet  # noqa: E402

FIELDS = ("time", "servings", "course", "cuisine", "meal_types", "difficulty")


def record(number: int, servings: int | None = 4) -> dict:
    return {
        "candidate_id": f"recipenlg:{number}",
        "title": "Garlic Noodles",
        "servings": servings,
        "ingredients": [
            {"original_text": "200 g noodles", "quantity_min": 200.0, "unit_dimension": "mass"},
            {"original_text": "salt to taste", "quantity_min": None, "unit_dimension": None},
        ],
        "instructions": [{"step_number": 1, "text": "Boil the noodles for 8 minutes."}],
        "triage": {"cuisine": "chinese", "course": "main"},
    }


def answer(servings: int = 4, **changes) -> dict:
    base = {
        "exclude_reason": "",
        "prep_minutes": 5,
        "cook_minutes": 10,
        "passive_minutes": 0,
        "time_basis": "stated",
        "servings": servings,
        "course": "main",
        "cuisine": "chinese",
        "meal_types": ["lunch", "dinner"],
        "difficulty": "easy",
        "line_estimates": [{"index": 2, "quantity": 0.5, "unit": "tsp", "basis": "salt for 4"}],
        "consumed_estimates": [],
        "evidence": dict.fromkeys(FIELDS, "e"),
        "confidence": dict.fromkeys(FIELDS, 0.8),
    }
    return {**base, **changes}


def response(content: dict | str, prompt: int = 3000, cached: int = 2000, completion: int = 500) -> dict:
    text = content if isinstance(content, str) else json.dumps(content)
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


class FakeClient:
    """Answers from a list, in order, and keeps the requests it got."""

    def __init__(self, *responses: dict) -> None:
        self.responses, self.requests = list(responses), []

    def __call__(self, request: dict) -> dict:
        self.requests.append(request)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class RequestTest(unittest.TestCase):
    def test_request_carries_the_v2_instructions_the_item_and_a_strict_schema(self) -> None:
        item = enrich.recipe_item(record(1))
        request = enrich.build_request(item, "gpt-5.4-mini", "low")
        system, user = request["messages"]
        self.assertEqual(request["model"], "gpt-5.4-mini")
        self.assertEqual(request["reasoning_effort"], "low")
        self.assertIn("line_estimates", system["content"])
        self.assertIn("`international` is only for a dish with no recognisable origin", system["content"])
        self.assertNotIn("v2_packet.py", system["content"])
        self.assertEqual(json.loads(user["content"]), item)
        self.assertEqual(item["ingredients"][1]["needs_amount"], True)
        schema = request["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertEqual(schema["schema"]["properties"]["cuisine"]["enum"], v2_packet.VOCAB["cuisine"])

    def test_schema_requires_every_property_at_each_level(self) -> None:
        def check(node: dict) -> None:
            if node.get("type") == "object":
                self.assertFalse(node["additionalProperties"])
                self.assertEqual(sorted(node["required"]), sorted(node["properties"]))
                for child in node["properties"].values():
                    check(child)
            if node.get("type") == "array":
                check(node["items"])

        schema = enrich.response_schema()
        check(schema)
        packet_keys = set(answer()) - {"exclude_reason"}
        self.assertEqual(set(schema["properties"]) - {"exclude_reason"}, packet_keys)

    def test_effort_is_left_out_when_empty_and_rejections_are_appended(self) -> None:
        item = enrich.recipe_item(record(1))
        request = enrich.build_request(item, "gpt-5.4-mini", "", ["servings is stated by the source as 4; keep it"])
        self.assertNotIn("reasoning_effort", request)
        self.assertIn("previous answer was rejected: servings is stated", request["messages"][1]["content"])


class ResultTest(unittest.TestCase):
    def test_answer_becomes_a_packet_result_marked_with_the_model(self) -> None:
        item = enrich.recipe_item(record(1))
        result = enrich.to_result(item, answer(), "gpt-5.4-mini")
        self.assertEqual(result["candidate_id"], "recipenlg:1")
        self.assertEqual(result["enriched_by"], "openai/gpt-5.4-mini")
        self.assertNotIn("exclude_reason", result)
        self.assertNotIn("consumed_estimates", result)
        self.assertEqual(v2_packet.check_recipe(item, result), [])

    def test_exclusion_is_a_packet_exclusion(self) -> None:
        item = enrich.recipe_item(record(1))
        result = enrich.to_result(item, answer(exclude_reason="not a food recipe: play dough"), "gpt-5.4-mini")
        self.assertEqual(
            result,
            {
                "candidate_id": "recipenlg:1",
                "exclude": "not a food recipe: play dough",
                "enriched_by": "openai/gpt-5.4-mini",
            },
        )
        self.assertEqual(v2_packet.check_recipe(item, result), [])

    def test_cost_prices_cached_input_apart(self) -> None:
        usage = {"prompt_tokens": 3000, "completion_tokens": 500, "prompt_tokens_details": {"cached_tokens": 2000}}
        expected = (1000 * 0.75 + 2000 * 0.075 + 500 * 4.5) / 1_000_000
        self.assertAlmostEqual(enrich.cost_usd(usage, "gpt-5.4-mini"), expected)
        self.assertAlmostEqual(
            enrich.cost_usd({"prompt_tokens": 10, "completion_tokens": 0}, "gpt-5.4-mini"), 10 * 0.75e-6
        )


class EnrichOneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.item = enrich.recipe_item(record(1))

    def test_valid_answer_is_accepted_at_once(self) -> None:
        client = FakeClient(response(answer()))
        outcome = enrich.enrich_one(self.item, client, "gpt-5.4-mini", "low")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(outcome["result"]["servings"], 4)
        self.assertEqual(outcome["calls"][0]["status"], "ok")
        self.assertGreater(outcome["calls"][0]["usd"], 0)

    def test_rejected_answer_is_asked_again_once_with_the_reasons(self) -> None:
        client = FakeClient(response(answer(servings=6)), response(answer()))
        outcome = enrich.enrich_one(self.item, client, "gpt-5.4-mini", "low")
        self.assertEqual(len(client.requests), 2)
        self.assertIn("servings is stated by the source as 4", client.requests[1]["messages"][1]["content"])
        self.assertEqual(outcome["result"]["servings"], 4)
        self.assertEqual([c["status"] for c in outcome["calls"]], ["rejected", "ok"])

    def test_two_rejections_make_it_failed(self) -> None:
        client = FakeClient(response(answer(servings=6)))
        outcome = enrich.enrich_one(self.item, client, "gpt-5.4-mini", "low")
        self.assertIsNone(outcome["result"])
        self.assertEqual(len(client.requests), 2)
        self.assertTrue(any("servings" in e for e in outcome["errors"]))

    def test_a_line_estimate_for_every_unquantified_line_is_required(self) -> None:
        client = FakeClient(response(answer(line_estimates=[])))
        outcome = enrich.enrich_one(self.item, client, "gpt-5.4-mini", "low")
        self.assertIsNone(outcome["result"])
        self.assertTrue(any("line_estimates for ingredient line 2" in e for e in outcome["errors"]))

    def test_text_that_is_not_json_is_a_rejection(self) -> None:
        client = FakeClient(response("not json"), response(answer()))
        outcome = enrich.enrich_one(self.item, client, "gpt-5.4-mini", "low")
        self.assertEqual(outcome["calls"][0]["status"], "rejected")
        self.assertIsNotNone(outcome["result"])


class KeyTest(unittest.TestCase):
    def test_only_the_key_line_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            path = Path(folder) / ".env"
            path.write_text("DATABASE_URL=postgres://secret\nOPENAI_API_KEY='sk-test'\nOTHER=1\n", encoding="utf-8")
            self.assertEqual(enrich.load_api_key(path), "sk-test")
            path.write_text("OTHER=1\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                enrich.load_api_key(path)

    def test_environment_wins(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}):
            self.assertEqual(enrich.load_api_key(Path("missing.env")), "sk-env")


class RunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        staging = Path(self.folder.name)
        self.paths = {
            "SELECTED": staging / "selected.jsonl",
            "MERGED": staging / "merged.jsonl",
            "FAILED": staging / "failed.jsonl",
            "USAGE": staging / "usage.jsonl",
            "SUMMARY": staging / "summary.json",
        }
        self.paths["SELECTED"].write_text("".join(json.dumps(record(n)) + "\n" for n in (1, 2, 3)), encoding="utf-8")
        patches = [mock.patch.object(enrich, name, path) for name, path in self.paths.items()]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.folder.cleanup)

    def args(self, **changes) -> argparse.Namespace:
        base = {
            "limit": None,
            "ids": None,
            "max_usd": 25.0,
            "workers": 2,
            "model": "gpt-5.4-mini",
            "reasoning_effort": "low",
            "retry_failed": False,
        }
        return argparse.Namespace(**{**base, **changes})

    def lines(self, name: str) -> list[dict]:
        path = self.paths[name]
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_run_writes_results_and_usage_and_resumes(self) -> None:
        client = FakeClient(response(answer()))
        self.assertEqual(enrich.run(self.args(limit=2), client), 0)
        self.assertEqual(len(self.lines("MERGED")), 2)
        self.assertEqual(len(self.lines("USAGE")), 2)
        self.assertEqual(self.lines("MERGED")[0]["enriched_by"], "openai/gpt-5.4-mini")
        self.assertEqual(enrich.run(self.args(), client), 0)
        self.assertEqual(
            sorted(r["candidate_id"] for r in self.lines("MERGED")), ["recipenlg:1", "recipenlg:2", "recipenlg:3"]
        )
        self.assertEqual(len(client.requests), 3)
        summary = json.loads(self.paths["SUMMARY"].read_text(encoding="utf-8"))
        self.assertEqual((summary["enriched"], summary["calls"]), (3, 3))

    def test_a_failed_recipe_is_recorded_and_not_asked_again(self) -> None:
        client = FakeClient(response(answer(servings=9)))
        enrich.run(self.args(ids=["recipenlg:1"]), client)
        self.assertEqual(self.lines("MERGED"), [])
        self.assertEqual(self.lines("FAILED")[0]["candidate_id"], "recipenlg:1")
        asked = len(client.requests)
        enrich.run(self.args(ids=["recipenlg:1"]), client)
        self.assertEqual(len(client.requests), asked)

    def test_the_cap_stops_the_run(self) -> None:
        client = FakeClient(response(answer()))
        self.assertEqual(enrich.run(self.args(max_usd=0.0001), client), 1)
        self.assertEqual(client.requests, [])

    def test_repeated_api_errors_stop_the_run(self) -> None:
        def failing(request: dict) -> dict:
            raise enrich.ApiError("HTTP 500")

        with mock.patch.object(enrich, "STOP_AFTER_API_ERRORS", 2):
            self.assertEqual(enrich.run(self.args(workers=1), failing), 1)
        self.assertEqual(self.lines("MERGED"), [])
        self.assertEqual(self.lines("FAILED"), [])


if __name__ == "__main__":
    unittest.main()
