"""Compile authored held-out episodes into frozen packets, and freeze the set.

Two commands complete the authoring workflow:

    python -m app.evaluation.heldout_set compile
    python -m app.evaluation.heldout_set freeze
    python -m app.evaluation.heldout_set verify

`compile` turns each authored episode's scenario into the same frozen packet
shape the v2 developer set uses, reusing `v2_packets.compile_packets` rather
than reimplementing it. Compiling is also the honest test of whether an episode
is usable: an episode whose candidate ingredients are not covered by its product
snapshot cannot be run by any system, and that surfaces here rather than on the
day the comparison is due.

**Gold never enters a packet.** The packet is what every compared system
receives. An episode's `gold` block holds the expected class, the required
clarification fields and the constraint answers; leaking any of it would hand
the answer to the systems being measured. `compile` reads only `scenario`, and
a test asserts no gold value appears anywhere in the compiled bundle.

`freeze` is the point of no return that `ADR-0020` section 2 describes. It runs
the authoring rules in strict mode, compiles every episode, records a digest
over both, and stamps the manifest. After that the set is evidence: a correction
creates a new version rather than editing in place, so that anything already
reported stays interpretable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.paths import repository_root
from app.evaluation.v2_packets import (
    PacketSourceFile,
    PacketSourceScenario,
    compile_packets,
)

SET_RELATIVE = Path("data/evaluation/heldout/v2")
CHECKER_RELATIVE = Path("scripts/check_heldout_episodes.py")


def _digest(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_episodes(set_dir: Path) -> list[dict[str, Any]]:
    episodes = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((set_dir / "episodes").glob("*.json"))]
    if not episodes:
        raise SystemExit(f"No episodes in {(set_dir / 'episodes')}. Nothing to compile.")
    return episodes


def to_source_scenario(episode: dict[str, Any]) -> PacketSourceScenario:
    """Project an episode onto packet source facts.

    Field-by-field on purpose. A `**episode["scenario"]` splat would silently
    carry along anything an author added, and the one thing that must never
    reach a packet is anything resembling an answer.
    """
    scenario = episode["scenario"]
    return PacketSourceScenario(
        scenario_id=episode["episode_id"],
        scenario_category=episode["category"],
        user_request=scenario["user_request"],
        conversation_history=scenario.get("conversation_history") or [],
        household_profile=scenario["household_profile"],
        pantry=scenario.get("pantry") or [],
        planning_horizon=scenario["planning_horizon"],
        locked_or_completed_meals=scenario.get("locked_or_completed_meals") or [],
        recipe_candidate_slugs=scenario["recipe_candidate_slugs"],
        fairprice_product_ids=scenario["fairprice_product_ids"],
    )


def compile_heldout_packets(root: Path | None = None) -> dict[str, Any]:
    root = root or repository_root()
    set_dir = root / SET_RELATIVE
    manifest = json.loads((set_dir / "set-manifest.json").read_text(encoding="utf-8"))
    episodes = load_episodes(set_dir)

    catalogs = {
        "ingredients": {
            item["normalized_name"]: item
            for item in json.loads((root / "data/ingredients/ingredients.json").read_text(encoding="utf-8"))
        },
        "recipes": {
            item["slug"]: item for item in json.loads((root / "data/recipes/recipes.json").read_text(encoding="utf-8"))
        },
        "products": {
            item["external_id"]: item
            for item in json.loads((root / "data/fixtures/fairprice-products.json").read_text(encoding="utf-8"))
        },
    }

    source = PacketSourceFile(
        schema_version="packet-source-v1",
        evaluation_role="held_out_set",
        provider_mode="fixture",
        observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        scenarios=[to_source_scenario(episode) for episode in episodes],
    )
    packets = compile_packets(source, **catalogs)
    payloads = [packet.model_dump(mode="json") for packet in packets]

    return {
        "schema_version": "heldout-packets-v2",
        "set_id": manifest["set_id"],
        "evaluation_role": "held_out_set",
        "live_api_used": False,
        "episode_count": len(episodes),
        "episode_set_sha256": _digest(episodes),
        "packet_set_sha256": _digest(payloads),
        "packets": payloads,
    }


def _run_checker(root: Path, strict: bool) -> None:
    """Delegate to the authoring checker instead of restating its rules.

    The checker is standard-library only so authors can run it without a
    container; importing it here would drag the backend's dependencies into that
    promise. Running it keeps one carrier for the rules.
    """
    command = [sys.executable, str(root / CHECKER_RELATIVE)]
    if strict:
        command.append("--strict")
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            "The set does not satisfy the authoring rules, so it cannot be frozen:\n"
            + (result.stdout or "")
            + (result.stderr or "")
        )


def freeze(root: Path | None = None) -> dict[str, Any]:
    root = root or repository_root()
    set_dir = root / SET_RELATIVE
    manifest_path = set_dir / "set-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("status") == "frozen":
        raise SystemExit(
            f"{manifest['set_id']} was frozen at {manifest.get('frozen_at')}. "
            "A frozen set is not edited: publish a corrected version with a new "
            "set_id, so that results already reported stay interpretable."
        )

    _run_checker(root, strict=True)
    bundle = compile_heldout_packets(root)

    manifest["status"] = "frozen"
    manifest["frozen_at"] = datetime.now(UTC).isoformat()
    manifest["frozen_digest"] = _digest(
        {"episodes": bundle["episode_set_sha256"], "packets": bundle["packet_set_sha256"]}
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (set_dir / "packets-v1.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify(root: Path | None = None) -> bool:
    """Recompute the digest of a frozen set and compare it with the manifest."""
    root = root or repository_root()
    manifest = json.loads((root / SET_RELATIVE / "set-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen":
        raise SystemExit(f"{manifest['set_id']} is not frozen yet; nothing to verify.")
    bundle = compile_heldout_packets(root)
    recomputed = _digest({"episodes": bundle["episode_set_sha256"], "packets": bundle["packet_set_sha256"]})
    return recomputed == manifest.get("frozen_digest")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["compile", "freeze", "verify"])
    parser.add_argument("--output", type=Path, help="compile only: where to write the bundle")
    args = parser.parse_args()
    root = repository_root()

    if args.command == "compile":
        _run_checker(root, strict=False)
        bundle = compile_heldout_packets(root)
        target = args.output or (root / SET_RELATIVE / "packets-v1.json")
        target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"Compiled {bundle['episode_count']} episodes into {target.relative_to(root).as_posix()}\n"
            f"  packet set sha256 {bundle['packet_set_sha256'][:16]}...\n"
            "  Compiling is not freezing. Run `freeze` when the set is complete and reviewed."
        )
        return 0

    if args.command == "freeze":
        manifest = freeze(root)
        print(
            f"Froze {manifest['set_id']} at {manifest['frozen_at']}\n"
            f"  digest {manifest['frozen_digest'][:16]}...\n"
            "  From here the set is evidence. Corrections create a new version."
        )
        return 0

    ok = verify(root)
    print("The frozen set matches its digest." if ok else "The frozen set no longer matches its digest.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
