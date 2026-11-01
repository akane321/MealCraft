from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cold_storage_mapping as mapping  # noqa: E402

PLAIN = {
    "product_id": "78715",
    "name": "Pura Fresh Milk 1L",
    "slug": "pura-fresh-milk-1l",
    "price": 3.5,
    "promo_price": 3.2,
    "average_weight": None,
    "in_stock": True,
    "url": "https://coldstorage.com.sg/product/pura-fresh-milk-1l",
}
WEIGHTED = {
    "product_id": "33396387",
    "name": "Aurora Premium Salmon Portion Norway 420g",
    "slug": "aurora-salmon",
    "price": 49.9,
    "promo_price": 42.9,
    "average_weight": "0.420",
    "in_stock": False,
    "url": "https://coldstorage.com.sg/product/aurora-salmon",
}


def observation(ingredient_id: str, query: str, products: list[dict], status: str = "ok") -> dict:
    return {
        "ingredient_id": ingredient_id,
        "query": query,
        "parser_version": "cold-storage-capture-v1",
        "status": status,
        "result_count": len(products),
        "products": products,
        "fetched_at": "2026-10-31T09:00:00+00:00",
    }


def proposal(ingredient_id: str, status: str, selected: list[dict], confidence: float = 0.9) -> dict:
    return {
        "ingredient_id": ingredient_id,
        "status": status,
        "selected": selected,
        "rejected": [],
        "search_again": [],
        "confidence": confidence,
        "notes": "",
        "enriched_by": "test",
        "review_status": "proposed",
    }


class PackPriceTest(unittest.TestCase):
    def test_a_plain_item_costs_its_promo_price(self):
        self.assertEqual(mapping.pack_price(PLAIN), 3.2)
        self.assertEqual(mapping.pack_price(dict(PLAIN, promo_price=None)), 3.5)

    def test_a_weighted_item_costs_the_per_kg_promo_price_times_its_average_weight(self):
        self.assertEqual(mapping.pack_price(WEIGHTED), 18.02)


class ProblemsTest(unittest.TestCase):
    products = {"ING_MILK": {"78715": PLAIN}}
    known = {"ING_MILK", "ING_SALMON"}

    def issues(self, item: dict) -> list[str]:
        return mapping.problems(item, self.products, self.known)

    def test_a_good_mapped_proposal_passes(self):
        good = proposal(
            "ING_MILK", "mapped", [{"product_id": "78715", "package_grams": 1030, "package_grams_basis": "1 L"}]
        )
        self.assertEqual(self.issues(good), [])

    def test_the_checks_catch_the_usual_mistakes(self):
        self.assertEqual(self.issues(proposal("ING_NOPE", "mapped", [])), ["unknown ingredient ING_NOPE"])
        self.assertIn("mapped without a selected product", self.issues(proposal("ING_MILK", "mapped", [])))
        self.assertIn("status 'not_purchased'", self.issues(proposal("ING_MILK", "not_purchased", [])))
        unseen = proposal("ING_MILK", "mapped", [{"product_id": "1", "package_grams": 0, "package_grams_basis": ""}])
        found = " | ".join(self.issues(unseen))
        for expected in ("was not returned", "package_grams 0", "no package_grams_basis"):
            self.assertIn(expected, found)
        self.assertIn("confidence 2", " ".join(self.issues(proposal("ING_MILK", "unavailable", [], confidence=2))))


class ExportTest(unittest.TestCase):
    def export(self, rows: list[dict], observations: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = {
                "OBSERVATIONS": root / "observations.jsonl",
                "MAPPING": root / "mapping.jsonl",
                "RUNTIME": root / "products" / "cold-storage-v1-snapshot.json",
            }
            mapping._write_jsonl(paths["OBSERVATIONS"], observations)
            mapping._write_jsonl(paths["MAPPING"], rows)
            with mock.patch.multiple(mapping, **paths):
                mapping.export()
            return json.loads(paths["RUNTIME"].read_text(encoding="utf-8"))

    def test_the_snapshot_has_the_contract_shape_and_skips_what_the_runtime_must_not_buy(self):
        observations = [
            observation("ING_MILK", "milk", [PLAIN]),
            observation("ING_SALMON", "salmon", [WEIGHTED]),
            observation("ING_BAD", "bad", [PLAIN], status="error"),
        ]
        rows = [
            proposal(
                "ING_MILK", "mapped", [{"product_id": "78715", "package_grams": 1030, "package_grams_basis": "1 L"}]
            ),
            proposal(
                "ING_SALMON",
                "mapped",
                [{"product_id": "33396387", "package_grams": 420, "package_grams_basis": "0.42 kg"}],
            ),
            proposal(
                "ING_LOW", "mapped", [{"product_id": "78715", "package_grams": 1, "package_grams_basis": "x"}], 0.5
            ),
            proposal("ING_GONE", "unavailable", []),
            dict(
                proposal(
                    "ING_FIXED", "mapped", [{"product_id": "78715", "package_grams": 1, "package_grams_basis": "x"}]
                ),
                review_status="owner_corrected",
            ),
        ]
        snapshot = self.export(rows, observations)
        self.assertEqual(
            {key: snapshot[key] for key in ("snapshot_version", "source", "min_confidence")},
            {"snapshot_version": "cold-storage-v1", "source": "cold_storage", "min_confidence": 0.6},
        )
        self.assertEqual(snapshot["fetched_from"], "2026-10-31T09:00:00+00:00")
        self.assertEqual(list(snapshot["ingredients"]), ["milk", "salmon"])
        self.assertEqual(
            snapshot["ingredients"]["milk"],
            {
                "status": "mapped",
                "review_status": "proposed",
                "products": [
                    {
                        "external_id": "cs-78715",
                        "name": "Pura Fresh Milk 1L",
                        "brand": None,
                        "category": None,
                        "package_grams": 1030,
                        "package_grams_basis": "1 L",
                        "price_sgd": 3.2,
                        "product_url": "https://coldstorage.com.sg/product/pura-fresh-milk-1l",
                        "in_stock": True,
                        "query": "milk",
                        "fetched_at": "2026-10-31T09:00:00+00:00",
                    }
                ],
            },
        )
        salmon = snapshot["ingredients"]["salmon"]["products"][0]
        self.assertEqual((salmon["price_sgd"], salmon["in_stock"]), (18.02, False))


if __name__ == "__main__":
    unittest.main()
