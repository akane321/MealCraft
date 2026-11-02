from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import enrich_v3_agents as agents  # noqa: E402
import enrich_v3_openai as oa  # noqa: E402
from test_enrich_v3_openai import answer, record  # noqa: E402


class AgentEnrichTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        staging = Path(folder.name)
        paths = {
            "SELECTED": staging / "selected.jsonl",
            "MERGED": staging / "merged.jsonl",
            "FAILED": staging / "failed.jsonl",
            "USAGE": staging / "usage.jsonl",
            "SUMMARY": staging / "summary.json",
        }
        self.paths = paths
        self.work = staging / "agent-enrich"
        # 1 is wave 1, 2 is merged by OpenAI already, 3 and 4 are pending.
        paths["SELECTED"].write_text("".join(json.dumps(record(n)) + "\n" for n in (1, 2, 3, 4)), encoding="utf-8")
        oa.append(paths["MERGED"], [oa.to_result(oa.recipe_item(record(2)), answer(), "gpt-5.4-mini")])
        wave1 = staging / "wave1.csv"
        wave1.write_text("candidate_id,source\nrecipenlg:1,recipenlg\n", encoding="utf-8")
        patches = [mock.patch.object(oa, name, path) for name, path in paths.items()]
        patches += [mock.patch.object(agents, "WORK", self.work), mock.patch.object(agents, "WAVE1_CSV", wave1)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_quiet(self, function, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            value = function(*args)
        return value, out.getvalue()

    def write_answers(self, name: str, lines: list[dict]) -> Path:
        path = self.work / name
        path.write_text("".join(json.dumps(line) + "\n" for line in lines) + "not json\n", encoding="utf-8")
        return path

    def test_export_writes_only_pending_wave_2_recipes_with_the_openai_input(self) -> None:
        paths, _ = self.run_quiet(agents.export, 1)
        self.assertEqual([p.name for p in paths], ["batch-001.jsonl", "batch-002.jsonl"])
        line = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(line, {"candidate_id": "recipenlg:3", "input": oa.recipe_item(record(3))})
        text = (self.work / "instructions.md").read_text(encoding="utf-8")
        self.assertIn(oa.instructions(), text)
        self.assertIn('"exclude_reason"', text)

    def test_check_reports_pass_and_errors_and_writes_nothing(self) -> None:
        self.work.mkdir()
        path = self.write_answers(
            "answers-001.jsonl",
            [
                {"candidate_id": "recipenlg:3", "answer": answer()},
                {"candidate_id": "recipenlg:4", "answer": answer(servings=2)},
            ],
        )
        code, out = self.run_quiet(agents.check, path)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "recipenlg:3: PASS")
        self.assertIn("servings is stated by the source as 4", lines[1])
        self.assertIn("None: candidate_id is not a selected recipe", lines[2])
        self.assertEqual(len(oa.existing(oa.MERGED)), 1)
        self.assertFalse(self.paths["FAILED"].exists())

    def test_import_appends_passes_records_failures_and_is_idempotent(self) -> None:
        self.work.mkdir()
        self.write_answers(
            "answers-001.jsonl",
            [
                {"candidate_id": "recipenlg:3", "answer": answer()},
                {"candidate_id": "recipenlg:4", "answer": answer(servings=2)},
                {"candidate_id": "recipenlg:2", "answer": answer()},
            ],
        )
        counts, _ = self.run_quiet(agents.import_answers, "claude-test")
        self.assertEqual(counts, {"added": 1, "failed": 1, "skipped": 2})
        merged = oa.existing(oa.MERGED)
        self.assertEqual([r["enriched_by"] for r in merged], ["openai/gpt-5.4-mini", "claude/claude-test"])
        self.assertEqual(merged[1]["candidate_id"], "recipenlg:3")
        self.assertEqual(oa.existing(oa.FAILED)[0]["by"], "claude/claude-test")
        summary = json.loads(self.paths["SUMMARY"].read_text(encoding="utf-8"))
        self.assertEqual(summary["enriched_by"], {"claude/claude-test": 1, "openai/gpt-5.4-mini": 1})
        self.assertEqual(summary["failed_last_by"], {"claude/claude-test": 1})

        self.run_quiet(agents.import_answers, "claude-test")
        self.assertEqual(len(oa.existing(oa.MERGED)), 2)
        self.assertEqual(len(oa.existing(oa.FAILED)), 1)

        self.write_answers("answers-002.jsonl", [{"candidate_id": "recipenlg:4", "answer": answer()}])
        counts, _ = self.run_quiet(agents.import_answers, "claude-test")
        self.assertEqual(counts["added"], 1)
        summary = json.loads(self.paths["SUMMARY"].read_text(encoding="utf-8"))
        self.assertEqual(summary["failed_last_by"], {})
        self.assertEqual(self.run_quiet(agents.pending)[0], [])


if __name__ == "__main__":
    unittest.main()
