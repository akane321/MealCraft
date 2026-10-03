from __future__ import annotations

import os
import subprocess

from app.core.paths import repository_root


def code_commit() -> str | None:
    """Return the supplied build revision, or the checkout revision when available."""

    if commit := os.getenv("CODE_COMMIT"):
        return commit[:64]
    try:
        found = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=repository_root(),
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return found.stdout.strip()[:64] or None
