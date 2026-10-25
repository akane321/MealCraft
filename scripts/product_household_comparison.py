"""Compare the product improvement pass on all full-default developer households."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation import full_default  # noqa: E402
from app.planning import product_path  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    original = product_path.improve_product_plan
    for steps in (0, 50):
        path = args.output / f"steps-{steps}.json"
        if path.exists():
            raise ValueError(f"Use a fresh output directory: {path} exists")

        def improve(problem, initial, losses, *, _steps=steps, **kwargs):
            if not _steps:
                return initial, {"algorithm": "beam-only", "steps": 0}
            return original(problem, initial, losses, steps=_steps, **kwargs)

        with patch.object(product_path, "improve_product_plan", improve):
            report, timings = full_default.evaluate(repeats=0)
        artifact = {
            "commit": commit,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "machine": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "steps": steps,
            "report": report,
            "timings": timings,
            "scope": "full-default developer households; fixture prices; one run per condition; no optimality claim",
        }
        path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: passed={report['passed']}", flush=True)


if __name__ == "__main__":
    main()
