from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from mealcraft_data.pipeline import run_pipeline
from mealcraft_data.utils import read_jsonl
from mealcraft_data.validation import validate_outputs

ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_demo_pipeline_is_reproducible_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            shutil.copytree(ROOT / "config", project_root / "config")
            input_path = ROOT / "data" / "fixtures" / "recipenlg_demo.csv"

            first = run_pipeline(project_root, input_path, 20, 5105, None, 200)
            first_recipes = (project_root / "data" / "curated" / "recipes.jsonl").read_bytes()
            second = run_pipeline(project_root, input_path, 20, 5105, None, 200)
            second_recipes = (project_root / "data" / "curated" / "recipes.jsonl").read_bytes()

            self.assertEqual(first, second)
            self.assertEqual(first_recipes, second_recipes)
            self.assertEqual(first["recipes_output"], 20)
            self.assertEqual(first["recipe_duplicate_ids"], 0)
            self.assertGreater(first["mapping_coverage"], 0.5)
            self.assertTrue(all(first["quality_gate"].values()))

            recipe_path = project_root / "data" / "curated" / "recipes.jsonl"
            ingredient_path = project_root / "data" / "curated" / "ingredients.jsonl"
            self.assertEqual(validate_outputs(recipe_path, ingredient_path), [])
            recipes = read_jsonl(recipe_path)
            self.assertTrue(all(recipe["nutrition"]["status"] == "not_computed" for recipe in recipes))


if __name__ == "__main__":
    unittest.main()
