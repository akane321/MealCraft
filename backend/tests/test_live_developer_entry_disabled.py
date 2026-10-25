import runpy
import sys
from pathlib import Path

import pytest

from app.core import config


@pytest.mark.parametrize("arguments", [[], ["--live"]])
def test_live_developer_entry_refuses_before_reading_settings_or_loading_clients(monkeypatch, arguments):
    script = Path(__file__).resolve().parents[1] / "scripts/evaluate_sprint2_live_dev.py"

    def forbidden():
        pytest.fail("The disabled entry must not load settings or credentials")

    monkeypatch.setattr(config, "get_settings", forbidden)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-real-key")
    monkeypatch.setattr(sys, "argv", [str(script), *arguments])
    with pytest.raises(SystemExit, match="Live developer evaluation is disabled"):
        runpy.run_path(str(script), run_name="__main__")
