import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def rule_parser_unless_asked(monkeypatch):
    """Tests never call a paid model: a developer's .env may select the live parser (the demo does)."""
    monkeypatch.setattr(get_settings(), "agent_parser_provider", "fixture")
    # Each test has its own catalog; a pool kept from another test would plan with its recipes.
    monkeypatch.setattr(get_settings(), "planning_pool_cache_seconds", 0)
