from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import redmart_mapping as mapping  # noqa: E402

ALLSPICE = {
    "product_id": "3124212075",
    "sku_id": "21260436730",
    "name": "Harras Turkish Allspice Pimento",
    "brand": "Harras",
    "price": 12.5,
    "original_price": None,
    "in_stock": True,
    "url": "https://www.lazada.sg/products/pdp-i3124212075.html",
    "image": "https://example.test/a.jpg",
}
DISCOUNT = dict(ALLSPICE, product_id="3434791625", name="Feral Allspice Drink", price=26.92, original_price=35.9)


def observation(ingredient_id: str, query: str, products: list[dict], status: str = "ok") -> dict:
    return {
        "ingredient_id": ingredient_id,
        "query": query,
        "page": 1,
        "parser_version": "redmart-capture-v1",
        "status": status,
        "result_count": len(products),
        "products": products,
        "fetched_at": "2026-11-01T09:00:00+00:00",
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


GOOD = [{"product_id": "3124212075", "package_grams": 50, "package_grams_basis": "no size printed; 50 g jar assumed"}]


class ProblemsTest(unittest.TestCase):
    products = {"ING_ALLSPICE": {"3124212075": ALLSPICE}}
    known = {"ING_ALLSPICE", "ING_DILL"}

    def issues(self, item: dict) -> list[str]:
        return mapping.problems(item, self.products, self.known)

    def test_a_good_mapped_proposal_passes(self):
        self.assertEqual(self.issues(proposal("ING_ALLSPICE", "mapped", GOOD)), [])

    def test_the_checks_catch_the_usual_mistakes(self):
        self.assertEqual(self.issues(proposal("ING_NOPE", "mapped", [])), ["unknown ingredient ING_NOPE"])
        self.assertIn("mapped without a selected product", self.issues(proposal("ING_ALLSPICE", "mapped", [])))
        self.assertIn("status 'not_purchased'", self.issues(proposal("ING_ALLSPICE", "not_purchased", [])))
        unseen = proposal(
            "ING_ALLSPICE", "mapped", [{"product_id": "1", "package_grams": 0, "package_grams_basis": ""}]
        )
        found = " | ".join(self.issues(unseen))
        for expected in ("was not returned", "package_grams 0", "no package_grams_basis"):
            self.assertIn(expected, found)
        self.assertIn("confidence 2", " ".join(self.issues(proposal("ING_ALLSPICE", "unavailable", [], confidence=2))))

    def test_a_product_cannot_be_selected_and_rejected(self):
        both = dict(proposal("ING_ALLSPICE", "mapped", GOOD), rejected=[{"product_id": "3124212075", "reason": "x"}])
        self.assertIn("3124212075 is both selected and rejected", self.issues(both))


class PacketTest(unittest.TestCase):
    def test_only_ingredients_with_a_redmart_candidate_are_packed_into_shards(self):
        release = {"ingredient_id": "ING_ALLSPICE", "canonical_name": "allspice", "forms": {}}
        rows = [release, dict(release, ingredient_id="ING_DILL", canonical_name="dill")]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "release").mkdir()
            mapping._write_jsonl(root / "release" / "ingredients.jsonl", rows)
            mapping._write_jsonl(root / "release" / "recipes.jsonl", [])
            mapping._write_jsonl(
                root / "observations.jsonl",
                [observation("ING_ALLSPICE", "allspice", [ALLSPICE, DISCOUNT]), observation("ING_DILL", "dill", [])],
            )
            with mock.patch.multiple(
                mapping, RELEASE=root / "release", OBSERVATIONS=root / "observations.jsonl", MAPPING=root / "m.jsonl"
            ):
                mapping.build_packets(2, root / "out")
            first = mapping._jsonl(root / "out" / "batch1.jsonl")
            self.assertEqual(len(first), 1)
            self.assertEqual(mapping._jsonl(root / "out" / "batch2.jsonl"), [])
            candidate = first[0]["candidates"][1]
            self.assertEqual(
                (candidate["product_id"], candidate["pack_price_sgd"], candidate["original_price_sgd"]),
                ("3434791625", 26.92, 35.9),
            )


class ExportTest(unittest.TestCase):
    def export(self, rows: list[dict], observations: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = {
                "OBSERVATIONS": root / "observations.jsonl",
                "MAPPING": root / "mapping.jsonl",
                "RUNTIME": root / "products" / "redmart-v1-snapshot.json",
            }
            mapping._write_jsonl(paths["OBSERVATIONS"], observations)
            mapping._write_jsonl(paths["MAPPING"], rows)
            with mock.patch.multiple(mapping, **paths):
                mapping.export()
            return json.loads(paths["RUNTIME"].read_text(encoding="utf-8"))

    def test_the_snapshot_has_the_contract_shape_and_skips_what_the_runtime_must_not_buy(self):
        observations = [
            observation("ING_ALLSPICE", "allspice", [ALLSPICE, DISCOUNT]),
            observation("ING_BAD", "bad", [ALLSPICE], status="error"),
        ]
        rows = [
            proposal("ING_ALLSPICE", "mapped", GOOD),
            proposal("ING_LOW", "mapped", GOOD, 0.5),
            proposal("ING_GONE", "unavailable", []),
            dict(proposal("ING_FIXED", "mapped", GOOD), review_status="owner_corrected"),
        ]
        snapshot = self.export(rows, observations)
        self.assertEqual(
            {key: snapshot[key] for key in ("snapshot_version", "source", "min_confidence")},
            {"snapshot_version": "redmart-v1", "source": "redmart", "min_confidence": 0.6},
        )
        self.assertEqual(snapshot["fetched_from"], "2026-11-01T09:00:00+00:00")
        self.assertEqual(list(snapshot["ingredients"]), ["allspice"])
        self.assertEqual(
            snapshot["ingredients"]["allspice"],
            {
                "status": "mapped",
                "review_status": "proposed",
                "products": [
                    {
                        "external_id": "rm-3124212075",
                        "name": "Harras Turkish Allspice Pimento",
                        "brand": "Harras",
                        "category": None,
                        "package_grams": 50,
                        "package_grams_basis": "no size printed; 50 g jar assumed",
                        "price_sgd": 12.5,
                        "product_url": "https://www.lazada.sg/products/pdp-i3124212075.html",
                        "in_stock": True,
                        "query": "allspice",
                        "fetched_at": "2026-11-01T09:00:00+00:00",
                    }
                ],
            },
        )


class SampleAndRecordTest(unittest.TestCase):
    def test_the_sample_is_stable_for_the_seed_and_the_default_seed_is_the_contract_one(self):
        self.assertEqual(mapping.DEFAULT_SEED, 20261101)
        rows = [proposal(f"ING_{n:02d}", "unavailable", []) for n in range(10)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mapping._write_jsonl(root / "mapping.jsonl", rows)
            mapping._write_jsonl(root / "observations.jsonl", [])
            drawn = []
            with mock.patch.multiple(
                mapping,
                MAPPING=root / "mapping.jsonl",
                OBSERVATIONS=root / "observations.jsonl",
                SAMPLE=root / "sample.json",
            ):
                for _ in range(2):
                    mapping.draw_sample(4, mapping.DEFAULT_SEED)
                    drawn.append([i["ingredient_id"] for i in json.loads((root / "sample.json").read_text())["items"]])
            self.assertEqual(drawn[0], drawn[1])
            self.assertEqual(len(drawn[0]), 4)

    def test_record_marks_the_sampled_rows_and_rejects_unknown_verdicts(self):
        rows = [proposal("ING_A", "unavailable", []), proposal("ING_B", "unavailable", [])]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mapping._write_jsonl(root / "mapping.jsonl", rows)
            (root / "sample.json").write_text(
                json.dumps({"seed": 1, "drawn_at": "t", "items": [{"ingredient_id": "ING_A"}]}), encoding="utf-8"
            )
            mapping._write_jsonl(root / "ok.jsonl", [{"ingredient_id": "ING_A", "verdict": "uncertain", "note": ""}])
            mapping._write_jsonl(root / "bad.jsonl", [{"ingredient_id": "ING_A", "verdict": "maybe"}])
            with mock.patch.multiple(
                mapping, MAPPING=root / "mapping.jsonl", SAMPLE=root / "sample.json", REVIEW=root / "review.json"
            ):
                with self.assertRaises(SystemExit):
                    mapping.record(root / "bad.jsonl")
                mapping.record(root / "ok.jsonl")
            statuses = {row["ingredient_id"]: row["review_status"] for row in mapping._jsonl(root / "mapping.jsonl")}
            self.assertEqual(statuses, {"ING_A": "owner_uncertain", "ING_B": "proposed"})
            self.assertEqual(json.loads((root / "review.json").read_text())["results"]["uncertain"], 1)


if __name__ == "__main__":
    unittest.main()
