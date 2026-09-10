"""Locate the committed data catalogs regardless of how the code is laid out.

MealCraft runs from two different directory shapes:

    host / CI     <repo>/backend/app/...      <repo>/backend/tests/...
                  with the catalogs at        <repo>/data/

    container     /app/app/...                /app/tests/
                  with ./data bind-mounted    /app/data/

Code that counted parent directories to reach the catalogs - `parents[2]` from a
test, `parents[3]` from an evaluation module - was correct in exactly one of
those shapes. On CI it worked; run through the documented
`docker compose exec backend ... pytest` command it resolved to `/data` and
fifteen tests failed on a missing file. Two test modules had already been
patched with an ad-hoc `Path("/app") if Path("/app/data").exists()` check, which
fixed those two and left the pattern in place for everything else.

Searching upward for the catalogs themselves is correct in both shapes, and in
any future one, because it asks where the data actually is instead of assuming
how deep the caller sits.
"""

from __future__ import annotations

from pathlib import Path

# A file that only ever exists at the root of the committed catalogs. Using a
# specific file rather than the `data` directory name avoids matching an
# unrelated `data` directory that happens to sit above the repository.
CATALOG_MARKER = Path("data") / "recipes" / "recipes.json"


class RepositoryRootNotFound(RuntimeError):
    """Raised when no ancestor directory contains the committed catalogs."""


def find_repository_root(start: Path | None = None) -> Path:
    """Return the directory that contains `data/recipes/recipes.json`.

    Searches `start` and its ancestors, nearest first. `start` defaults to this
    module's directory, so callers do not need to know their own depth.
    """
    origin = (start or Path(__file__).parent).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / CATALOG_MARKER).is_file():
            return candidate
    raise RepositoryRootNotFound(
        f"No ancestor of {origin} contains {CATALOG_MARKER.as_posix()}. "
        "Run from a checkout, or from a container with ./data mounted."
    )


def repository_root() -> Path:
    """The repository root for the current layout."""
    return find_repository_root()


def data_root() -> Path:
    """The committed `data/` directory for the current layout."""
    return repository_root() / "data"
