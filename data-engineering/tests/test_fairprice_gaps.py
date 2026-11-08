from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fairprice_gaps as gaps  # noqa: E402


def ingredient(ingredient_id: str, name: str, recipes: int) -> dict:
    return {
        "ingredient_id": ingredient_id,
        "canonical_name": name,
        "recipe_occurrences": recipes,
        "forms": {ingredient_id: {"nutrition_form": f"{name}, raw", "unit_grams": []}},
    }


INGREDIENTS = [
    ingredient("ING_SALT", "salt", 50),
    ingredient("ING_TURKEY", "turkey", 84),
    ingredient("ING_LARD", "lard", 20),
    ingredient("ING_PISTACHIO", "pistachio", 20),
    ingredient("ING_WATER", "water", 900),
    ingredient("ING_ICE", "ice", 10),
    ingredient("ING_STOCK_CUBE", "stock cube", 7),
]
EMPTY_LAYERS = {name: set() for name, _ in gaps.LAYERS}


def product(in_stock: bool = True) -> dict:
    return {"external_id": "x", "price_sgd": 1.0, "package_grams": 100, "in_stock": in_stock}


class PricedNamesTest(unittest.TestCase):
    def test_mapped_with_stock_counts(self):
        mapping = {"salt": {"status": "mapped", "products": [product()]}}
        self.assertEqual(gaps.priced_names(mapping), {"salt"})

    def test_out_of_stock_only_does_not_count(self):
        mapping = {"salt": {"status": "mapped", "products": [product(False)]}}
        self.assertEqual(gaps.priced_names(mapping), set())

    def test_one_in_stock_product_is_enough(self):
        mapping = {"salt": {"status": "mapped", "products": [product(False), product()]}}
        self.assertEqual(gaps.priced_names(mapping), {"salt"})

    def test_not_purchased_and_unavailable_do_not_count(self):
        mapping = {"water": {"status": "not_purchased"}, "a": {"status": "unavailable", "products": [product()]}}
        self.assertEqual(gaps.priced_names(mapping), set())

    def test_a_missing_status_means_mapped(self):
        self.assertEqual(gaps.priced_names({"a": {"products": [product()]}}), {"a"})


class RankingTest(unittest.TestCase):
    layers = dict(EMPTY_LAYERS, fairprice={"salt"})

    def names(self, layers):
        return [row["ingredient_id"] for row in gaps.unpriced(INGREDIENTS, layers)]

    def test_priced_water_and_ice_are_left_out(self):
        names = self.names(self.layers)
        for left_out in ("ING_SALT", "ING_WATER", "ING_ICE"):
            self.assertNotIn(left_out, names)

    def test_most_used_first_and_ties_by_id(self):
        self.assertEqual(self.names(self.layers), ["ING_TURKEY", "ING_LARD", "ING_PISTACHIO", "ING_STOCK_CUBE"])

    def test_any_layer_prices_an_ingredient(self):
        self.assertNotIn("ING_TURKEY", self.names(dict(self.layers, manual={"turkey"})))

    def test_cumulative_share_reaches_one(self):
        rows = gaps.unpriced(INGREDIENTS, self.layers)
        shares = gaps.cumulative_share(rows, sum(r["recipes"] for r in rows))
        self.assertEqual(shares[-1], 1.0)
        self.assertEqual(shares, sorted(shares))

    def test_cumulative_share_of_nothing_is_zero(self):
        self.assertEqual(gaps.cumulative_share([{"recipes": 0}], 0), [0.0])


class CoverageTest(unittest.TestCase):
    def test_each_layer_counts_only_what_earlier_ones_miss(self):
        layers = {
            "fairprice": {"salt", "turkey"},
            "cold_storage": {"turkey", "lard"},
            "redmart": set(),
            "manual": {"lard"},
        }
        result = gaps.coverage(INGREDIENTS, layers)
        self.assertEqual(result["bought_ingredients"], 5)
        self.assertEqual(result["by_layer"], {"fairprice": 2, "cold_storage": 1, "redmart": 0, "manual": 0})
        self.assertEqual(result["priced"], 3)
        self.assertEqual(result["unpriced"], 2)
        self.assertEqual(result["share"], 0.6)

    def test_nothing_priced(self):
        result = gaps.coverage(INGREDIENTS, EMPTY_LAYERS)
        self.assertEqual((result["priced"], result["share"]), (0, 0.0))


class FilesTest(unittest.TestCase):
    def test_absent_layer_files_price_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(gaps.load_layers(Path(folder)), EMPTY_LAYERS)

    def test_layers_read_the_snapshot_ingredients(self):
        with tempfile.TemporaryDirectory() as folder:
            body = {"ingredients": {"salt": {"status": "mapped", "products": [product()]}}}
            (Path(folder) / "fairprice-v2-snapshot.json").write_text(json.dumps(body), encoding="utf-8")
            layers = gaps.load_layers(Path(folder))
        self.assertEqual(layers["fairprice"], {"salt"})
        self.assertEqual(layers["redmart"], set())

    def test_runtime_name(self):
        self.assertEqual(gaps.runtime_name("ING_LIME_ZEST"), "lime_zest")


def observation(ingredient_id: str, query: str, ids: list[str], status: str = "ok") -> dict:
    products = [{"product_id": i, "name": f"p{i}", "final_price": 2.0, "in_stock": True, "url": f"u{i}"} for i in ids]
    return {"ingredient_id": ingredient_id, "query": query, "status": status, "products": products, "fetched_at": "t"}


class PacketTest(unittest.TestCase):
    def test_observations_merge_and_the_first_sighting_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "a.jsonl", Path(folder) / "b.jsonl"
            first.write_text(json.dumps(observation("ING_TURKEY", "turkey", ["1"])) + "\n", encoding="utf-8")
            second.write_text(
                json.dumps(observation("ING_TURKEY", "turkey breast", ["1", "2"]))
                + "\n"
                + json.dumps(observation("ING_LARD", "lard", ["9"], status="error"))
                + "\n",
                encoding="utf-8",
            )
            found = gaps.observed_products(first, second, Path(folder) / "missing.jsonl")
        self.assertEqual(set(found["ING_TURKEY"]), {"1", "2"})
        self.assertEqual(found["ING_TURKEY"]["1"]["query"], "turkey")
        self.assertNotIn("ING_LARD", found)

    def test_packet_marks_products_the_earlier_review_rejected(self):
        rows = [{"ingredient_id": "ING_TURKEY", "canonical_name": "turkey", "recipes": 84}]
        by_id = {row["ingredient_id"]: row for row in INGREDIENTS}
        history = {"ING_TURKEY": {"status": "unavailable", "rejected": [{"product_id": "1", "reason": "cured ham"}]}}
        products = {"ING_TURKEY": {"1": {"product_id": "1", "name": "ham"}, "2": {"product_id": "2", "name": "breast"}}}
        packet = gaps.build_packets(rows, by_id, history, products, {"ING_TURKEY": ["1 turkey"]})[0]
        reasons = {c["product_id"]: c["previously_rejected"] for c in packet["candidates"]}
        self.assertEqual(reasons, {"1": "cured ham", "2": None})
        self.assertEqual(packet["previous_status"], "unavailable")
        self.assertEqual(packet["recipe_lines"], ["1 turkey"])

    def test_packet_for_an_unseen_ingredient_has_no_candidates(self):
        rows = [{"ingredient_id": "ING_LARD", "canonical_name": "lard", "recipes": 20}]
        by_id = {row["ingredient_id"]: row for row in INGREDIENTS}
        packet = gaps.build_packets(rows, by_id, {}, {}, {})[0]
        self.assertEqual(packet["candidates"], [])
        self.assertIsNone(packet["previous_status"])

    def test_shards_deal_rows_round_robin(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = gaps.write_packets([{"n": i} for i in range(5)], 2, Path(folder))
            sizes = [len(path.read_text(encoding="utf-8").splitlines()) for path in paths]
        self.assertEqual(sizes, [3, 2])

    def test_worklist_is_utf8_with_bom_and_ranked(self):
        rows = gaps.unpriced(INGREDIENTS, EMPTY_LAYERS)
        with tempfile.TemporaryDirectory() as folder:
            path = gaps.write_worklist(rows, sum(r["recipes"] for r in rows), Path(folder))
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as handle:
                table = list(csv.DictReader(handle))
        self.assertEqual([row["rank"] for row in table[:2]], ["1", "2"])
        self.assertEqual(table[0]["ingredient_id"], "ING_TURKEY")


if __name__ == "__main__":
    unittest.main()
