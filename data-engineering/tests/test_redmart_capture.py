from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capture_redmart_snapshot as capture  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "redmart"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseSearchTest(unittest.TestCase):
    def test_a_results_page_gives_the_total_and_every_raw_item(self):
        total, items = capture.parse_search(page("search_results.json"))
        self.assertEqual((total, len(items)), (1966, 5))

    def test_only_redmart_items_are_kept_by_seller_name_seller_id_or_icon(self):
        _, items = capture.parse_search(page("search_results.json"))
        self.assertEqual(
            [item["itemId"] for item in items if capture.is_redmart(item)],
            ["3124212075", "2932350459", "3434791625", "222"],
        )

    def test_an_empty_result_and_a_page_without_redmart_are_no_match_not_errors(self):
        self.assertEqual(capture.parse_search(page("search_empty.json")), (0, []))
        _, items = capture.parse_search(page("search_no_redmart.json"))
        self.assertEqual([item for item in items if capture.is_redmart(item)], [])

    def test_html_challenge_pages_and_other_shapes_are_schema_drift(self):
        for body in (
            "<html><body>Please slide to verify: punish</body></html>",
            "<html>x5sec captcha</html>",
            '{"ret": ["FAIL_SYS_USER_VALIDATE"]}',
            '{"mods": {"listItems": "nope"}}',
            '{"mods": {}}',  # no listItems at all is not an empty result
            '{"mods": {"listItems": null}, "mainInfo": {"totalResults": "0"}}',
            "[]",
        ):
            with self.assertRaises(capture.ProductSchemaDriftError, msg=body):
                capture.parse_search(body)

    def test_the_challenge_marker_is_named_in_the_error(self):
        with self.assertRaisesRegex(capture.ProductSchemaDriftError, "captcha"):
            capture.parse_search("<html>captcha</html>")


class TrimTest(unittest.TestCase):
    def trimmed(self, item_id: str) -> dict:
        _, items = capture.parse_search(page("search_results.json"))
        return capture.trim_product(next(item for item in items if item["itemId"] == item_id))

    def test_trim_keeps_the_contract_fields_with_the_https_url(self):
        product = self.trimmed("3124212075")
        self.assertEqual(
            product,
            {
                "product_id": "3124212075",
                "sku_id": "21260436730",
                "name": "Harras Turkish Allspice Pimento",
                "brand": "Harras",
                "price": 12.5,
                "original_price": None,
                "in_stock": True,
                "url": "https://www.lazada.sg/products/pdp-i3124212075.html",
                "image": "https://sg-test-11.slatic.net/p/f9d7d835417eec7238081102e3bfe310.jpg",
            },
        )

    def test_a_discount_keeps_both_prices_and_a_missing_stock_flag_is_not_assumed(self):
        product = self.trimmed("3434791625")
        self.assertEqual((product["price"], product["original_price"]), (26.92, 35.9))
        self.assertFalse(self.trimmed("222")["in_stock"])

    def test_an_item_missing_a_field_or_with_a_bad_price_is_schema_drift(self):
        good = {"itemId": "1", "name": "x", "price": "1.5", "inStock": True, "itemUrl": "//www.lazada.sg/p"}
        self.assertEqual(capture.trim_product(good)["price"], 1.5)
        with self.assertRaises(capture.ProductSchemaDriftError):
            capture.trim_product({key: value for key, value in good.items() if key != "name"})
        with self.assertRaises(capture.ProductSchemaDriftError):
            capture.trim_product(dict(good, price="free"))

    def test_a_stock_flag_that_is_not_a_boolean_is_schema_drift_and_a_full_url_is_kept(self):
        good = {"itemId": "1", "name": "x", "price": "1.5", "inStock": True, "itemUrl": "//www.lazada.sg/p"}
        for flag in ("false", 0, None):
            with self.assertRaises(capture.ProductSchemaDriftError, msg=repr(flag)):
                capture.trim_product(dict(good, inStock=flag))
        full = capture.trim_product(dict(good, itemUrl="https://www.lazada.sg/p"))
        self.assertEqual(full["url"], "https://www.lazada.sg/p")


class RequestTest(unittest.TestCase):
    def test_the_url_is_the_ajax_search_with_a_dashed_slug(self):
        self.assertEqual(
            capture.search_url("Water Chestnut", 2),
            "https://www.lazada.sg/tag/water-chestnut/?ajax=true&q=Water%20Chestnut&page=2",
        )

    def test_a_redirect_is_never_followed(self):
        handler = capture._NoRedirect()
        request = urllib.request.Request("https://www.lazada.sg/x")
        self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, "https://www.lazada.sg/login"))


class QueryPlanTest(unittest.TestCase):
    def test_plausible_needs_every_query_word_in_one_redmart_name(self):
        self.assertTrue(capture.plausible("allspice", [{"name": "Harras Turkish Allspice Pimento"}]))
        self.assertFalse(capture.plausible("water chestnut", [{"name": "Chestnut Spread"}]))
        self.assertFalse(capture.plausible("allspice", []))

    def test_queries_are_the_canonical_name_one_simpler_form_then_other_stores_search_again(self):
        self.assertEqual(
            capture.queries_for("ground sumac", ["sumac spice", "za'atar"]), ["ground sumac", "sumac", "sumac spice"]
        )
        self.assertEqual(
            capture.queries_for("sumac", ["Sumac", "sumac powder", "x", "y"]), ["sumac", "sumac powder", "x"]
        )
        self.assertEqual(capture.queries_for("dill", []), ["dill"])

    def test_page_two_is_read_only_when_page_one_has_no_redmart_item_and_more_results_exist(self):
        self.assertTrue(capture.needs_page_two({"products": [], "result_count": 1966}))
        self.assertFalse(capture.needs_page_two({"products": [{}], "result_count": 1966}))
        self.assertFalse(capture.needs_page_two({"products": [], "result_count": 12}))


def listing(names: list[str], total: int = 12) -> str:
    items = [
        {
            "itemId": str(i),
            "name": name,
            "price": "2.5",
            "inStock": True,
            "itemUrl": f"//www.lazada.sg/p{i}",
            "sellerName": "RedMart",
        }
        for i, name in enumerate(names, 1)
    ]
    return json.dumps({"mods": {"listItems": items}, "mainInfo": {"totalResults": total}})


class FakeResponse:
    def __init__(self, body: str):
        self.status, self.headers, self._body = 200, {}, body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Answers each request in turn: a body (200), an int (that HTTP error) or an exception; records the URLs."""

    def __init__(self, *answers):
        self.answers, self.urls = list(answers), []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        answer = self.answers.pop(0)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(request.full_url, answer, "x", {}, io.BytesIO())
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


class CaptureLoopTest(unittest.TestCase):
    def run_loop(self, plan, *answers, done=None, finished=None, limit=500):
        opener, handle, naps = FakeOpener(*answers), io.StringIO(), []
        result = capture.run(
            plan,
            {} if done is None else done,
            set() if finished is None else finished,
            handle,
            opener=opener,
            limit=limit,
            delay=1.0,
            sleep=naps.append,
        )
        rows = [json.loads(line) for line in handle.getvalue().splitlines()]
        return result, rows, opener, naps

    def test_a_plausible_hit_stops_the_ingredient_and_goes_to_the_next(self):
        plan = [("ING_A", ["allspice", "pimento"]), ("ING_B", ["sumac"])]
        (requests, stopped), rows, opener, naps = self.run_loop(plan, listing(["Turkish Allspice"]), listing(["Sumac"]))
        self.assertEqual((requests, stopped, [r["ingredient_id"] for r in rows]), (2, None, ["ING_A", "ING_B"]))
        self.assertEqual((naps, len(opener.urls)), ([1.0, 1.0], 2))

    def test_the_next_query_is_tried_when_the_hit_is_not_plausible(self):
        plan = [("ING_A", ["water chestnut", "chestnut"])]
        (requests, _), rows, _, _ = self.run_loop(plan, listing(["Chestnut Spread"]), listing(["Roasted Chestnut"]))
        self.assertEqual((requests, [r["query"] for r in rows]), (2, ["water chestnut", "chestnut"]))

    def test_page_two_only_when_page_one_has_no_redmart_item_and_more_results_exist(self):
        (requests, _), rows, opener, _ = self.run_loop([("ING_A", ["sumac"])], listing([], 500), listing(["Sumac"]))
        self.assertEqual((requests, [r["page"] for r in rows]), (2, [1, 2]))
        self.assertIn("page=2", opener.urls[1])
        (requests, _), rows, _, _ = self.run_loop([("ING_A", ["sumac"])], listing([], 12))
        self.assertEqual((requests, [r["page"] for r in rows]), (1, [1]))
        (requests, _), rows, _, _ = self.run_loop([("ING_A", ["sumac"])], listing(["Other Thing"], 500))
        self.assertEqual((requests, [r["page"] for r in rows]), (1, [1]))

    def test_a_404_is_a_no_tag_row_and_the_run_goes_on(self):
        plan = [("ING_A", ["swede turnip"]), ("ING_B", ["sumac"])]
        (requests, stopped), rows, _, _ = self.run_loop(plan, 404, listing(["Sumac"]))
        self.assertEqual((requests, stopped), (2, None))
        self.assertEqual(
            {key: rows[0][key] for key in ("status", "result_count", "products", "page")},
            {"status": "no_tag", "result_count": 0, "products": [], "page": 1},
        )
        self.assertEqual(rows[1]["status"], "ok")

    def test_403_429_5xx_a_redirect_a_challenge_page_and_a_dropped_connection_stop_the_run(self):
        for answer in (403, 429, 500, 503, 302, "<html>punish</html>", "<html>captcha</html>", OSError("reset")):
            with self.subTest(answer=answer):
                plan = [("ING_A", ["a"]), ("ING_B", ["b"])]
                (requests, stopped), rows, _, naps = self.run_loop(plan, answer, listing(["b"]))
                self.assertEqual((requests, len(rows), rows[0]["status"], naps), (1, 1, "error", []))
                self.assertIn("Stopping", stopped)

    def test_the_request_cap_stops_before_the_next_request(self):
        plan = [("ING_A", ["a"]), ("ING_B", ["b"]), ("ING_C", ["c"])]
        (requests, stopped), rows, opener, _ = self.run_loop(plan, listing(["x"]), listing(["y"]), limit=2)
        self.assertEqual((requests, len(rows), len(opener.urls)), (2, 2, 2))
        self.assertIn("request cap 2", stopped)

    def test_a_rerun_skips_what_is_captured_and_resumes(self):
        plan = [("ING_A", ["allspice"]), ("ING_B", ["no match", "sumac"]), ("ING_C", ["dill"])]
        first, rows, _, _ = self.run_loop(plan, listing(["Allspice"]), 404, 403)
        self.assertEqual(first[0], 3)
        stored = [row for row in rows if row["status"] != "error"]  # the 403 error row is not "captured"
        done = {(r["ingredient_id"], r["query"], r["page"]): r for r in stored}
        finished = {r["ingredient_id"] for r in stored if capture.plausible(r["query"], r["products"])}
        self.assertEqual(finished, {"ING_A"})
        (requests, stopped), rows, _, _ = self.run_loop(
            plan, listing(["Sumac"]), listing(["Dill"]), done=done, finished=finished
        )
        self.assertEqual((requests, stopped, [r["query"] for r in rows]), (2, None, ["sumac", "dill"]))

    def test_captured_counts_ok_and_no_tag_rows_but_not_errors(self):
        rows = [
            {
                "ingredient_id": "ING_A",
                "query": "allspice",
                "page": 1,
                "status": "ok",
                "result_count": 1,
                "products": [{"name": "Allspice"}],
            },
            {
                "ingredient_id": "ING_B",
                "query": "swede",
                "page": 1,
                "status": "no_tag",
                "result_count": 0,
                "products": [],
            },
            {"ingredient_id": "ING_C", "query": "dill", "page": 1, "status": "error", "error": "HTTPError: 403"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "observations.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            old, capture.OUTPUT = capture.OUTPUT, path
            try:
                done, finished = capture.captured()
            finally:
                capture.OUTPUT = old
        self.assertEqual(set(done), {("ING_A", "allspice", 1), ("ING_B", "swede", 1)})
        self.assertEqual(finished, {"ING_A"})


if __name__ == "__main__":
    unittest.main()
