"""Record that a reviewer has checked held-out episodes.

    python scripts/mark_reviewed.py --reviewer backend ho-standard-001 ho-standard-002
    python scripts/mark_reviewed.py --reviewer backend --all
    python scripts/mark_reviewed.py --reviewer backend ho-budget_package-004 --note "budget checked by hand"

Sets `reviewed_by` and, with --note, appends a dated line to `review_notes`. It
then runs the authoring checker, which refuses a reviewer who authored the
episode or owns a system its category evaluates. On refusal every file is put
back as it was, so a rejected review leaves nothing half-recorded.

Standard library only, no container.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPISODES = ROOT / "data" / "evaluation" / "heldout" / "v2" / "episodes"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviewer", required=True, help="the reviewer's role from set-manifest.json")
    parser.add_argument("--note", help="appended to review_notes with today's date")
    parser.add_argument("--all", action="store_true", help="every episode not yet reviewed")
    parser.add_argument("episodes", nargs="*", help="episode ids, e.g. ho-standard-001")
    args = parser.parse_args()

    if args.all == bool(args.episodes):
        parser.error("name episodes or pass --all, not both and not neither")

    if args.all:
        paths = [
            p
            for p in sorted(EPISODES.glob("ho-*.json"))
            if json.loads(p.read_text(encoding="utf-8"))["reviewed_by"] is None
        ]
    else:
        paths = [EPISODES / f"{episode_id}.json" for episode_id in args.episodes]
        missing = [p.stem for p in paths if not p.is_file()]
        if missing:
            parser.error(f"no such episode: {', '.join(missing)}")

    originals = {p: p.read_bytes() for p in paths}
    for path in paths:
        episode = json.loads(path.read_text(encoding="utf-8"))
        episode["reviewed_by"] = args.reviewer
        if args.note:
            line = f"[review {datetime.date.today().isoformat()} {args.reviewer}] {args.note}"
            episode["review_notes"] = f"{episode['review_notes']}\n{line}" if episode.get("review_notes") else line
        path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    checker = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_heldout_episodes.py")])
    if checker.returncode != 0:
        for path, content in originals.items():
            path.write_bytes(content)
        print(f"\nReview not recorded; {len(paths)} file(s) restored.", file=sys.stderr)
        return 1
    print(f"\nRecorded {args.reviewer} as reviewer on {len(paths)} episode(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
