from __future__ import annotations

import collections
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import select_v3_candidates as select  # noqa: E402


def recipe(recipe_id: str, cuisine: str, course: str) -> dict:
    return {"recipe_id": recipe_id, "cuisine": cuisine, "course": course}


def row(number: int, bucket: str, cuisine: str, course: str = "main", servings: int | None = None) -> dict:
    return {
        "candidate_id": f"recipenlg:{number}",
        "bucket": bucket,
        "cuisine": cuisine,
        "course": course,
        "servings": servings,
        "title": f"dish {number}",
    }


class SelectTest(unittest.TestCase):
    def test_title_key_ignores_case_and_spacing(self) -> None:
        self.assertEqual(select.title_key("  Garlic   NOODLES "), select.title_key("garlic noodles"))

    def test_priced_uses_the_importers_normalized_name(self) -> None:
        names = frozenset({"fish_sauce"})
        self.assertTrue(select.priced("ING_FISH_SAUCE", names))
        self.assertFalse(select.priced("ING_BELACAN", names))

    def test_cap_keeps_usable_courses_first_then_recipe_id(self) -> None:
        added = [
            recipe("RCP2_B", "american", "dessert"),
            recipe("RCP2_C", "american", "side"),
            recipe("RCP2_A", "american", "dessert"),
            recipe("RCP2_D", "thai", "dessert"),
        ]
        base = collections.Counter({"american": 8, "thai": 1})
        kept, cut = select.cap_by_label(base, added, 10)
        self.assertEqual([r["recipe_id"] for r in kept], ["RCP2_A", "RCP2_C", "RCP2_D"])
        self.assertEqual(dict(cut), {"american": 1})

    def test_cap_with_no_room_keeps_none_of_the_label(self) -> None:
        kept, cut = select.cap_by_label(
            collections.Counter({"american": 10}), [recipe("RCP2_A", "american", "side")], 10
        )
        self.assertEqual(kept, [])
        self.assertEqual(cut["american"], 1)

    def test_allocation_follows_targets_caps_by_supply_and_never_picks_the_american_bucket(self) -> None:
        rows = [row(n, "chinese", "chinese") for n in range(100)]
        rows += [row(1000 + n, "indian", "indian") for n in range(100)]
        rows += [row(2000 + n, "korean", "korean") for n in range(3)]
        rows += [row(3000 + n, "american", "southern_us") for n in range(50)]
        picked = select.allocate(rows, 60)
        counts = collections.Counter(r["bucket"] for r in picked)
        self.assertEqual(len(picked), 60)
        self.assertEqual(counts["american"], 0)
        self.assertEqual(counts["korean"], 3)
        self.assertGreater(counts["chinese"], counts["indian"])  # targets 1200 against 700

    def test_mains_come_first_and_other_courses_only_when_they_run_out(self) -> None:
        rows = [row(n, "thai", "thai", "main") for n in range(5)] + [
            row(10 + n, "thai", "thai", "dessert") for n in range(5)
        ]
        rows += [row(20, "thai", "thai", "side_soup_salad")]
        picked = select.allocate(rows, 8)
        courses = collections.Counter(r["course"] for r in picked)
        self.assertEqual(courses, {"main": 5, "side_soup_salad": 1, "dessert": 2})

    def test_local_dishes_are_all_taken_and_titles_never_repeat(self) -> None:
        rows = [row(n, "southeast_asian", "malaysian_singaporean", "dessert") for n in range(4)]
        rows += [row(100 + n, "southeast_asian", "indonesian") for n in range(10)]
        rows += [{**row(200, "chinese", "chinese"), "title": "dish 100"}]
        picked = select.allocate(rows, 6)
        self.assertEqual(sum(r["cuisine"] == "malaysian_singaporean" for r in picked), 4)
        titles = [r["title"] for r in picked]
        self.assertEqual(len(titles), len(set(titles)))

    def test_order_is_deterministic(self) -> None:
        rows = [row(n, "chinese", "chinese", servings=n % 2 or None) for n in range(30)]
        self.assertEqual(select.allocate(rows, 10), select.allocate(list(reversed(rows)), 10))

    def test_a_larger_total_keeps_every_first_wave_pick(self) -> None:
        rows = [row(n, "chinese", "chinese", servings=n % 2 or None) for n in range(40)]
        rows += [row(100 + n, "thai", "thai", "dessert") for n in range(20)]
        rows += [{**row(200, "indian", "indian"), "title": "dish 3"}]
        first_rows = select.allocate(rows, 10)
        first = {r["candidate_id"]: r["bucket"] for r in first_rows}
        grown = select.extend(rows, first, 30)
        self.assertEqual(len(grown), 30)
        self.assertLessEqual(set(first), {r["candidate_id"] for r in grown})
        by_id = {r["candidate_id"]: r for r in rows}
        for r in grown:
            self.assertEqual(r["wave"], 1 if r["candidate_id"] in first else 2)
            self.assertEqual({k: v for k, v in r.items() if k != "wave"}, by_id[r["candidate_id"]])
        titles = [r["title"] for r in grown]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(grown, select.extend(list(reversed(rows)), first, 30))
        self.assertEqual({r["candidate_id"] for r in select.extend(rows, first, 10)}, set(first))

    def test_a_first_wave_pick_that_no_longer_qualifies_stops_the_run(self) -> None:
        rows = [row(n, "chinese", "chinese") for n in range(5)]
        with self.assertRaises(SystemExit):
            select.extend(rows, {"recipenlg:999": "chinese"}, 5)


if __name__ == "__main__":
    unittest.main()
