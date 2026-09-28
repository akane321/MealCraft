import pytest

from app.core.config import Settings, get_settings

# CI runs without a .env, and the ops tests expect what it sees: no API keys and the fixture parser. A
# developer's .env selects the OpenAI parser and holds a key for the demo, and the API tests build their
# own Settings(...) which would read it from the repository root. So no Settings built in this process,
# the cached one or a test's own, reads a .env: each starts from the class defaults, as in CI.
Settings.model_config["env_file"] = None


@pytest.fixture(autouse=True)
def rule_parser_unless_asked(monkeypatch):
    """Tests never call a paid model: a developer's shell may still select the live parser."""
    monkeypatch.setattr(get_settings(), "agent_parser_provider", "fixture")
    # Each test has its own catalog; a pool kept from another test would plan with its recipes.
    monkeypatch.setattr(get_settings(), "planning_pool_cache_seconds", 0)
