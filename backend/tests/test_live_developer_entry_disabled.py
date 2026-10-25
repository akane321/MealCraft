import runpy
import sys

import pytest

from app.core import config
from app.core.paths import repository_root


def test_disabled_developer_entry_is_packaged_and_mounted():
    root = repository_root()
    compose = root / "compose.yaml"
    if not compose.is_file():
        pytest.skip("Packaging files are checked in the source checkout")
    assert "COPY backend/scripts/evaluate_sprint2_live_dev.py ./backend/scripts/evaluate_sprint2_live_dev.py" in (
        root / "backend/Dockerfile"
    ).read_text(encoding="utf-8")
    assert (
        "- ./backend/scripts/evaluate_sprint2_live_dev.py:/app/backend/scripts/evaluate_sprint2_live_dev.py:ro"
        in compose.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("arguments", [[], ["--live"]])
def test_live_developer_entry_refuses_before_reading_settings_or_loading_clients(monkeypatch, arguments):
    script = repository_root() / "backend/scripts/evaluate_sprint2_live_dev.py"

    def forbidden():
        pytest.fail("The disabled entry must not load settings or credentials")

    monkeypatch.setattr(config, "get_settings", forbidden)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-real-key")
    monkeypatch.setattr(sys, "argv", [str(script), *arguments])
    with pytest.raises(SystemExit, match="Live developer evaluation is disabled"):
        runpy.run_path(str(script), run_name="__main__")
