"""Every release directory the backend code reads is mounted into the backend and worker containers.

The Dockerfile copies no release files, so a release the code names but compose does not mount
exists on the host only: host pytest passes and the same tests fail inside the container.
"""

from __future__ import annotations

import re

import pytest

from app.core.paths import repository_root

RELEASE_DIR = re.compile(r"data-engineering/data/release/(v\d+(?:\.\d+)*)")


def _services(compose: str) -> dict[str, str]:
    """Split compose.yaml into its top-level service blocks (two-space indented names)."""
    blocks: dict[str, str] = {}
    name = None
    for line in compose.splitlines():
        header = re.match(r"^  ([a-z][\w-]*):\s*$", line)
        if header:
            name = header.group(1)
            blocks[name] = ""
        elif name:
            blocks[name] += line + "\n"
    return blocks


def test_every_release_the_backend_reads_is_mounted():
    root = repository_root()
    compose_file = root / "compose.yaml"
    if not compose_file.exists():
        pytest.skip("compose.yaml is not inside the container")
    named = {
        version
        for path in (root / "backend/app").rglob("*.py")
        for version in RELEASE_DIR.findall(path.read_text(encoding="utf-8"))
    }
    assert "v2.1" in named and "v2.2" in named
    services = _services(compose_file.read_text(encoding="utf-8"))
    for service in ("backend", "worker"):
        mounted = {
            m.group(1)
            for m in re.finditer(r"- \./data-engineering/data/release/(v[\d.]+):/app/\S+:ro", services[service])
        }
        assert named <= mounted, f"{service} lacks release mounts {sorted(named - mounted)}"
