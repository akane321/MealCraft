from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_release_v2 as build  # noqa: E402
import build_release_v3 as v3  # noqa: E402
import test_build_release_v3 as harness  # noqa: E402
import v3_corrections as corrections  # noqa: E402

HEADER = "recipe_id,field,old_value,new_value,reason,reviewer"
# Ten released recipes: two v2.2 ones and eight added; thai and chinese are at the 20% cap (2 of 10).
CUISINES = ["thai", "thai", "chinese", "chinese", "italian", "korean", "japanese", "french", "greek", "indian"]
RELEASED = {
    f"RCP2_{n:012d}": {
        "recipe_id": f"RCP2_{n:012d}",
        "title": f"Dish {n}",
        "cuisine": cuisine,
        "course": "main",
        "servings": 4,
    }
    for n, cuisine in enumerate(CUISINES, 1)
}
V22 = {"RCP2_000000000009", "RCP2_000000000010"}
TABLE = [
    "RCP2_000000000005,cuisine,italian,greek,ok,amy",  # 2: no problem
    "RCP2_000000000099,servings,4,2,unknown id,amy",  # 3
    "RCP2_000000000009,servings,4,2,a v2.2 record,amy",  # 4
    "RCP2_000000000004,title,Dish 4,Dish four,not a field,amy",  # 5
    "RCP2_000000000004,cuisine,chinese,international,outside the vocabulary,amy",  # 6
    "RCP2_000000000005,servings,4,51,out of range,amy",  # 7
    "RCP2_000000000005,course,soup,side,old value is not the released one,amy",  # 8
    "RCP2_000000000006,course,main,side,first,amy",  # 9
    "RCP2_000000000006,course,main,salad,duplicate,amy",  # 10
    "RCP2_000000000007,servings,4,3,,amy",  # 11: empty reason
    "RCP2_000000000008,withdraw,,yes,unfit,amy",  # 12
    "RCP2_000000000008,servings,4,2,withdrawn and corrected,amy",  # 13
    "RCP2_000000000002,cuisine,thai,korean,ok,amy",  # 14: no problem
    "RCP2_000000000007,cuisine,japanese,chinese,over the cap,amy",  # 15
    "RCP2_000000000001,withdraw,thai,yes,old value given,amy",  # 16
]
EXPECTED = {
    3: "is not in release v3",
    4: "is a release v2.2 record",
    5: "field 'title' is not one of",
    6: "'international' is not a cuisine",
    7: "'51' is not a whole number 1-50",
    8: "old_value 'soup' is not the released course 'main'",
    10: "is already in row 9",
    11: "reason is empty",
    12: "is withdrawn, so it takes no other correction",
    15: "cuisine chinese would have 3 of 10 recipes, over the 20% cap (2)",
    16: "old_value must be empty for withdraw",
}


def write_table(folder: Path, lines: list[str]) -> Path:
    path = folder / "v3-corrections.csv"
    path.write_bytes(("﻿" + "\r\n".join([HEADER, *lines]) + "\r\n").encode())  # as Excel saves it
    return path


class CheckerTest(unittest.TestCase):
    def test_every_problem_is_named_by_its_row(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            rows = corrections.read_table(write_table(Path(folder), TABLE))
        problems = corrections.check_rows(rows, V22, RELEASED)
        by_row = {}
        for problem in problems:
            row, text = problem.split(": ", 1)
            by_row.setdefault(int(row.split()[1]), []).append(text)
        self.assertEqual(sorted(by_row), sorted(EXPECTED))
        for row, text in EXPECTED.items():
            self.assertTrue(any(text in p for p in by_row[row]), (row, by_row[row]))

    def test_the_committed_table_validates(self) -> None:
        rows = corrections.read_table()
        released = corrections.read_release("v3")
        self.assertEqual(corrections.check_rows(rows, set(corrections.read_release("v2.2")), released), [])

    def test_a_row_the_release_already_carries_passes(self) -> None:
        released = {**RELEASED, "RCP2_000000000005": {**RELEASED["RCP2_000000000005"], "cuisine": "greek"}}
        with tempfile.TemporaryDirectory() as folder:
            rows = corrections.read_table(write_table(Path(folder), TABLE[:1]))
        self.assertEqual(corrections.check_rows(rows, V22, released), [])

    def test_a_gbk_table_is_named_not_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t.csv"
            path.write_bytes((HEADER + "\r\nRCP2_000000000005,cuisine,italian,greek,ok,张三\r\n").encode("gbk"))
            with self.assertRaisesRegex(SystemExit, "not UTF-8; in Excel save as 'CSV UTF-8"):
                corrections.read_table(path)

    def test_case_spaces_and_a_float_cell_are_read_as_the_vocabulary_value(self) -> None:
        lines = ["RCP2_000000000005,Cuisine,Italian ,Greek,ok,amy", "RCP2_000000000006,servings,4.0,3.0,ok,amy"]
        with tempfile.TemporaryDirectory() as folder:
            rows = corrections.read_table(write_table(Path(folder), lines))
        self.assertEqual(corrections.check_rows(rows, V22, RELEASED), [])
        bad = {**rows[0], "new_value": "malaysian", "row": 2}
        self.assertIn("malaysian_singaporean", corrections.check_rows([bad], V22, RELEASED)[0])

    def test_export_lists_only_the_added_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sheet.csv"
            released = {rid: {**r, "servings_basis": "estimated"} for rid, r in RELEASED.items()}
            self.assertEqual(corrections.export(path, released, V22), 8)
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(lines[0], "recipe_id,title,cuisine,course,servings,servings_basis")
        self.assertEqual(lines[1], "RCP2_000000000001,Dish 1,thai,main,4,estimated")
        self.assertEqual(len(lines), 9)


class WithdrawTest(unittest.TestCase):
    def test_withdraw_writes_slug_reason_and_reviewer_and_is_idempotent(self) -> None:
        released = {
            "RCP2_5A2BDB57937A": {"recipe_id": "RCP2_5A2BDB57937A", "title": "Bacon And Chicken Stir-Fry For Your Cat"},
            "RCP2_AB7A10D4A81E": {"recipe_id": "RCP2_AB7A10D4A81E", "title": "Flax And Mango Cold Soup"},
        }
        rows = [
            {"recipe_id": "RCP2_AB7A10D4A81E", "field": "withdraw", "reason": "Contains rum.", "reviewer": "amy"},
            {"recipe_id": "RCP2_5A2BDB57937A", "field": "withdraw", "reason": "Pet food.", "reviewer": "amy"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "withdrawn.json"
            shutil.copyfile(corrections.WITHDRAWN, path)
            before = json.loads(path.read_text(encoding="utf-8"))["recipes"]
            self.assertEqual(corrections.withdraw(rows, released, path), 2)
            once = path.read_bytes()
            self.assertEqual(corrections.withdraw(rows, released, path), 0)
            self.assertEqual(path.read_bytes(), once)
            after = json.loads(once)["recipes"]
        self.assertEqual(len(after), len(before) + 1)  # the cat recipe was already listed: updated, not added twice
        self.assertIn(
            {"slug": "v2-flax-and-mango-cold-soup-ab7a10d4a81e", "reason": "Contains rum.", "reviewer": "amy"}, after
        )
        self.assertEqual(after[0]["slug"], before[0]["slug"])
        self.assertEqual((after[0]["reason"], after[0]["reviewer"]), ("Pet food.", "amy"))


def toy_record(number: int) -> tuple[dict, dict]:
    """A candidate and its enrichment result that `build_release_v2.build_recipe` builds."""
    line = {
        "original_text": "4 tomatoes",
        "canonical_ingredient_id": "ING_TOMATO",
        "quantity_min": 4.0,
        "quantity_max": None,
        "unit_normalized": "piece",
        "preparation": [],
        "optional": False,
    }
    record = {
        "candidate_id": f"recipenlg:{number}",
        "title": f"Tomato plate {number}",
        "source": "recipenlg",
        "source_id": str(number),
        "source_license": "x",
        "servings": None,
        "ingredients": [line, {**line, "original_text": "2 tomatoes", "quantity_min": 2.0}],
        "instructions": [{"step_number": 1, "text": "Slice and serve."}],
        "stated_durations": [],
    }
    fields = ("time", "servings", "course", "cuisine", "meal_types", "difficulty")
    result = {
        "servings": 4,
        "prep_minutes": 5,
        "cook_minutes": 0,
        "passive_minutes": 0,
        "time_basis": "estimated",
        "course": "side",
        "cuisine": "chinese",
        "meal_types": ["lunch"],
        "difficulty": "easy",
        "enriched_by": "openai/gpt-5.4-mini",
        "evidence": dict.fromkeys(fields, "model"),
        "confidence": dict.fromkeys(fields, 0.5),
    }
    return record, result


FORMS = {
    "ING_TOMATO": {
        "unit_grams": [{"unit": "piece", "grams": 100.0}],
        "nutrition_per_100g": dict.fromkeys(build.NUTRIENTS, 20.0),
    }
}
RULES = {
    "ING_TOMATO": {
        "canonical_name": "tomato",
        "food_group": "vegetable",
        "allergens": [],
        "allergen_status": "confirmed",
        "dietary_origin": "plant",
    }
}


class BuildAppliesCorrectionsTest(unittest.TestCase):
    def test_cuisine_and_servings_rows_are_built_with_nutrition_per_reviewed_serving(self) -> None:
        records, results = {}, {}
        for number in (1, 2):
            records[f"recipenlg:{number}"], results[f"recipenlg:{number}"] = toy_record(number)
        rid = v3.recipe_id_of("recipenlg:1")
        rows = [
            {"row": 2, "recipe_id": rid, "field": "cuisine", "old_value": "chinese", "new_value": "thai"},
            {"row": 3, "recipe_id": rid, "field": "servings", "old_value": "4", "new_value": "2"},
        ]
        for row in rows:
            row.update(reason="checked", reviewer="amy")
        problems, found = v3.apply_reviews(results, {rid: rows})
        self.assertEqual((problems, found), ([], {rid}))
        built, drops = v3.rebuild(records, results, FORMS, RULES, {})
        self.assertEqual(drops, [])
        fixed, other = sorted(built, key=lambda r: r["recipe_id"] != rid)
        self.assertEqual(fixed["recipe_id"], rid)
        self.assertEqual((fixed["cuisine"], fixed["servings"]), ("thai", 2))
        self.assertEqual((other["cuisine"], other["servings"]), ("chinese", 4))
        # 600 g at 20 kcal per 100 g = 120 kcal: 30 per serving for four, 60 for the reviewed two.
        self.assertEqual((fixed["nutrition"]["energy_kcal"], other["nutrition"]["energy_kcal"]), (60.0, 30.0))
        self.assertEqual(fixed["enrichment"]["evidence"]["servings"], "reviewed by amy: checked (was 4)")
        self.assertEqual(fixed["enrichment"]["confidence"]["cuisine"], 1.0)
        self.assertEqual(other["enrichment"]["evidence"]["servings"], "model")

    def test_an_old_value_that_is_not_the_built_value_is_a_problem(self) -> None:
        record, result = toy_record(1)
        rid = v3.recipe_id_of(record["candidate_id"])
        row = {"row": 2, "recipe_id": rid, "field": "course", "old_value": "main", "new_value": "soup", "reviewer": "a"}
        row["reason"] = "checked"
        problems, _ = v3.apply_reviews({record["candidate_id"]: result}, {rid: [row]})
        self.assertEqual(problems, ["row 2: old_value 'main' is not the built course 'side'"])

    def test_only_the_corrected_ids_are_exempt_from_the_first_build_check(self) -> None:
        def digest(recipe: dict) -> str:
            return hashlib.sha256(json.dumps(recipe, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

        before = harness.inputs(harness.V22, [harness.recipe(20, "chinese"), harness.recipe(21, "thai")], [])
        first = {
            key: digest(r)
            for key, r in harness.released(harness.assemble(*before)).items()
            if key >= "RCP2_000000000020"
        }
        reviewed = harness.recipe(20, "korean")  # as the build makes it once the cuisine row is applied
        row = {"row": 2, "recipe_id": reviewed["recipe_id"], "field": "cuisine", "new_value": "korean"}
        args = harness.inputs(harness.V22, [reviewed, harness.recipe(21, "thai")], [])
        with self.assertRaises(SystemExit):
            harness.assemble(*args, first_build=first)
        files = harness.assemble(*args, first_build=first, reviews=[row])
        self.assertEqual(harness.released(files)[reviewed["recipe_id"]]["cuisine"], "korean")
        manifest = json.loads(files["release_manifest.json"])
        self.assertEqual(manifest["derived_from"]["reviewed_corrections"]["rows_by_field"], {"cuisine": 1})
        self.assertIn("## Reviewed corrections", files["quality_report.md"].decode())
        changed = harness.inputs(harness.V22, [reviewed, harness.recipe(21, "american")], [])
        with self.assertRaises(SystemExit):  # another first-build record changed: still stops the build
            harness.assemble(*changed, first_build=first, reviews=[row])
        with self.assertRaises(SystemExit):  # a row whose value the released recipe does not carry
            harness.assemble(*args, first_build=first, reviews=[{**row, "new_value": "thai"}])

    def test_a_corrected_recipe_that_the_build_dropped_is_named_with_its_reason(self) -> None:
        rid = v3.recipe_id_of("recipenlg:99")
        row = {"row": 7, "recipe_id": rid, "field": "servings", "new_value": "2"}
        args = harness.inputs(harness.V22, [], [harness.recipe(21, "thai")], drops=("recipenlg:99",))
        with self.assertRaisesRegex(SystemExit, r"table rows 7 \(reviewed incomplete: milk\)"):
            harness.assemble(*args, reviews=[row])

    def test_a_crlf_table_hashes_as_its_lf_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            crlf, lf = Path(folder) / "crlf.csv", Path(folder) / "lf.csv"
            crlf.write_bytes(b"a,b\r\n1,2\r\n")
            lf.write_bytes(b"a,b\n1,2\n")
            self.assertEqual(v3.table_sha256(crlf), v3.table_sha256(lf))

    def test_an_empty_table_changes_no_output(self) -> None:
        args = harness.inputs(harness.V22, [harness.recipe(20, "chinese")], [harness.recipe(21, "thai")])
        self.assertEqual(harness.assemble(*args), harness.assemble(*args, reviews=[]))


if __name__ == "__main__":
    unittest.main()
