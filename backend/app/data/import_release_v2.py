import argparse
from pathlib import Path

from app.data.release_v2 import import_release_v2, release_dir
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import data-engineering release v2 next to the curated catalog; skips a release already imported."
    )
    parser.add_argument("--release-dir", type=Path, default=None, help=f"default: {release_dir()}")
    parser.add_argument("--force", action="store_true", help="re-import even when the recorded digest matches")
    args = parser.parse_args()

    with SessionLocal() as session:
        report = import_release_v2(session, args.release_dir, force=args.force)
    print(report.summary())
    if report.recipes_skipped:
        print("Skipped (fewer than two ingredient lines or no instruction): " + ", ".join(report.recipes_skipped))


if __name__ == "__main__":
    main()
