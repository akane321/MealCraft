import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def rule_parser_unless_asked(monkeypatch):
    """Tests never call a paid model: a developer's .env may select the live parser (the demo does)."""
    monkeypatch.setattr(get_settings(), "agent_parser_provider", "fixture")
