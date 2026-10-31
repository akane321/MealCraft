from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import manual_prices as manual  # noqa: E402

RELEASE = Path(__file__).resolve().parent / "fixtures" / "manual" / "ingredients.jsonl"
TODAY = date(2026, 11, 2)
HEADER = [
    "rank",
    "ingredient_id",
    "ingredient",
    "recipes",
    "platform",
    "product_name",
    "product_url",
    "price_sgd",
    "package_size",
    "package_unit",
    "in_stock",
    "observed_date",
    "note",
]


def row(rank="1", ingredient_id="ING_SAFFRON", **filled) -> dict:
    base = dict.fromkeys(HEADER, "") | {"rank": rank, "ingredient_id": ingredient_id, "ingredient": "x", "recipes": "9"}
    return base | filled


def good(**changes) -> dict:
    return (
        row(
            platform="shopee",
            product_name="Saffron 1g",
            product_url="https://shopee.sg/saffron-i.1.2",
            price_sgd="S$4.50",
            package_size="1",
            package_unit="g",
            in_stock="y",
            observed_date="2026-11-01",
        )
        | changes
    )


def write_sheet(directory: str, rows: list[dict], newline: str = "\r\n") -> Path:
    """An Excel-style sheet: UTF-8 with BOM, CRLF."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, HEADER, lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    path = Path(directory) / "price-sheet.csv"
    path.write_bytes(b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8"))
    return path


class ManualPricesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def check(self, rows, newline="\r\n"):
        return manual.check_sheet(write_sheet(self.tmp.name, rows, newline), RELEASE, TODAY)

    def test_excel_style_values_pass_and_blank_rows_are_skipped(self):
        for price in ("S$4.50", "4.5", "$4.5", "SGD 4.50", "4.50", "1,234.00"):
            problems, products = self.check([good(price_sgd=price), row(rank="2", ingredient_id="ING_MIRIN")])
            self.assertEqual((problems, len(products)), ([], 1), price)
        self.assertEqual(products[0][1]["price_sgd"], 1234.0)

    def test_bom_and_lf_or_crlf_both_read(self):
        for newline in ("\r\n", "\n"):
            problems, products = self.check([good()], newline)
            self.assertEqual((problems, len(products)), ([], 1))
        self.assertEqual(products[0][0]["rank"], "1")  # the BOM did not glue itself to the first header

    def test_a_note_alone_leaves_the_row_blank(self):
        problems, products = self.check([row(note="not sold")])
        self.assertEqual((problems, products), ([], []))

    def test_problems_are_named_by_rank_and_line(self):
        problems, products = self.check(
            [
                good(price_sgd="4.505"),
                good(rank="2", ingredient_id="ING_MIRIN", package_unit="oz", in_stock="maybe"),
                good(rank="3", product_url="https://www.lazada.sg/p", platform="shopee"),
                good(rank="4", observed_date="2026-11-03"),
                good(rank="5", observed_date="1/11/2026"),
                good(rank="6", price_sgd="0"),
                good(rank="7", package_size="-2"),
                good(rank="8", platform="ebay"),
                good(rank="9", ingredient_id="ING_NOPE"),
            ]
        )
        self.assertEqual(products, [])
        text = "\n".join(problems)
        for expected in (
            "rank 1 (line 2): price_sgd '4.505'",
            "rank 2 (line 3): package_unit 'oz'",
            "rank 2 (line 3): in_stock 'maybe'",
            "rank 3 (line 4): product_url host 'www.lazada.sg' does not belong to shopee",
            "rank 4 (line 5): observed_date 2026-11-03 is in the future",
            "rank 5 (line 6): observed_date '1/11/2026'",
            "rank 6 (line 7): price_sgd '0'",
            "rank 7 (line 8): package_size '-2'",
            "rank 8 (line 9): platform 'ebay'",
            "rank 9 (line 10): ingredient_id 'ING_NOPE'",
        ):
            self.assertIn(expected, text)

    def test_hosts_match_the_platform_exactly_or_as_a_subdomain(self):
        cases = [
            ("shopee", "https://shopee.sg/a", True),
            ("shopee", "https://www.shopee.sg/a", True),
            ("shopee", "https://notshopee.sg/a", False),
            ("shopee", "https://shopee.sg.evil.com/a", False),
            ("lazada", "https://www.lazada.sg/products/pdp-i1.html", True),
            ("amazon", "https://www.amazon.sg/dp/B0", True),
            ("amazon", "https://www.amazon.com/dp/B0", False),
            ("redmart", "https://redmart.lazada.sg/x", True),
            ("redmart", "https://www.lazada.sg/products/pdp-i1.html", True),
            ("other", "https://example.com/a", True),
            ("other", "ftp://example.com/a", False),
            ("other", "example.com/a", False),
        ]
        for platform, url, ok in cases:
            problems, _ = self.check([good(platform=platform, product_url=url)])
            self.assertEqual(problems == [], ok, (platform, url, problems))

    def test_a_count_needs_a_known_weight_and_a_volume_falls_back_to_one_gram_per_ml(self):
        problems, _ = self.check([good(package_size="3", package_unit="count")])  # saffron: no piece weight
        self.assertIn("rank 1 (line 2): 3 count has no known weight", problems[0])
        _, products = self.check(
            [
                good(ingredient_id="ING_COCONUT_MILK", package_size="2", package_unit="count"),
                good(rank="2", ingredient_id="ING_COCONUT_MILK", package_size="400", package_unit="ml"),
                good(rank="3", ingredient_id="ING_MIRIN", package_size="0.5", package_unit="l"),
                good(rank="4", package_size="1.5", package_unit="kg"),
            ]
        )
        by_rank = {r["rank"]: p for r, p in products}
        self.assertEqual(by_rank["1"]["package_grams"], 800.0)
        self.assertIn("400 g per item", by_rank["1"]["package_grams_basis"])
        self.assertEqual(by_rank["2"]["package_grams"], 400.0)
        self.assertIn("assumed", by_rank["2"]["package_grams_basis"])
        self.assertEqual(by_rank["3"]["package_grams"], 525.0)  # the record's own 1.05 g/ml
        self.assertIn("release record", by_rank["3"]["package_grams_basis"])
        self.assertEqual(by_rank["4"]["package_grams"], 1500.0)

    def test_export_numbers_repeated_rows_and_writes_the_snapshot(self):
        sheet = write_sheet(
            self.tmp.name,
            [
                good(),
                row(rank="2", ingredient_id="ING_MIRIN"),
                good(
                    product_name="Saffron 2g",
                    price_sgd="7",
                    package_size="2",
                    platform="amazon",
                    in_stock="n",
                    product_url="https://www.amazon.sg/dp/B0",
                    observed_date="2026-10-30",
                ),
                good(rank="3", ingredient_id="ING_COCONUT_MILK", package_size="1", package_unit="count"),
            ],
        )
        out = Path(self.tmp.name) / "out" / "manual-v1-snapshot.json"
        snapshot = manual.export(sheet, RELEASE, out, TODAY)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), snapshot)
        self.assertNotIn(b"\r", out.read_bytes())
        self.assertEqual((snapshot["snapshot_version"], snapshot["source"]), ("manual-v1", "manual"))
        self.assertEqual(list(snapshot["ingredients"]), ["coconut_milk", "saffron"])
        saffron = snapshot["ingredients"]["saffron"]
        self.assertEqual((saffron["status"], saffron["review_status"]), ("mapped", "owner_recorded"))
        first, second = saffron["products"]
        self.assertEqual((first["external_id"], second["external_id"]), ("mn-1-1", "mn-1-2"))
        self.assertEqual((first["retailer"], second["retailer"]), ("shopee", "amazon"))
        self.assertEqual((first["price_sgd"], second["in_stock"]), (4.5, False))
        self.assertEqual(first["fetched_at"], "2026-11-01T00:00:00+08:00")
        self.assertEqual(
            (snapshot["fetched_from"], snapshot["fetched_to"]), (second["fetched_at"], first["fetched_at"])
        )
        self.assertEqual(snapshot["ingredients"]["coconut_milk"]["products"][0]["external_id"], "mn-3-1")

    def test_export_writes_nothing_while_any_row_has_a_problem(self):
        sheet = write_sheet(self.tmp.name, [good(), good(rank="2", price_sgd="free")])
        out = Path(self.tmp.name) / "manual-v1-snapshot.json"
        self.assertIsNone(manual.export(sheet, RELEASE, out, TODAY))
        self.assertFalse(out.exists())

    def test_one_rank_cannot_name_two_ingredients(self):
        problems, _ = self.check([good(), good(ingredient_id="ING_MIRIN")])
        self.assertIn("rank is already used by ING_SAFFRON", problems[0])

    def test_a_sheet_missing_a_column_stops(self):
        path = Path(self.tmp.name) / "bad.csv"
        path.write_text("rank,ingredient_id\n1,ING_SAFFRON\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            manual.read_sheet(path)


if __name__ == "__main__":
    unittest.main()
