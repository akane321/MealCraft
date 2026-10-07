from datetime import UTC, datetime

from app.products import provider as module


def test_fixture_reuses_ranking_not_results_timestamps_or_limits(monkeypatch):
    records = [
        {
            "external_id": identity,
            "name": "Brown Rice",
            "ingredient_keys": ["brown_rice"],
            "price_sgd": price,
            "product_url": "https://example.invalid/rice",
        }
        for identity, price in [("expensive", 3), ("cheap", 2)]
    ]
    monkeypatch.setattr(module, "_fixture_records", lambda _path: records)
    calls = []
    tokenize = module.search_tokens

    def counted(value):
        calls.append(value)
        return tokenize(value)

    class Clock:
        tick = 0

        @classmethod
        def now(cls, _zone):
            cls.tick += 1
            return datetime(2026, 10, 7, 0, 0, cls.tick, tzinfo=UTC)

    monkeypatch.setattr(module, "search_tokens", counted)
    monkeypatch.setattr(module, "datetime", Clock)
    provider = module.FixtureProductProvider("unused.json")
    first = provider.search("brown_rice", limit=1)
    assert [item.external_id for item in first] == ["cheap"]
    first[0].price_sgd = 99
    ranked_calls = len(calls)
    second = provider.search(" BROWN-RICE ", limit=5)
    assert len(calls) == ranked_calls
    assert [(item.external_id, item.price_sgd) for item in second] == [("cheap", 2), ("expensive", 3)]
    assert second[0] is not first[0]
    assert second[0].fetched_at > first[0].fetched_at

    assert provider.search("missing", limit=5) == []
    empty_calls = len(calls)
    assert provider.search("missing", limit=5) == []
    assert len(calls) == empty_calls
    other = module.FixtureProductProvider("another.json")
    assert [item.external_id for item in other.search("brown rice", limit=5)] == ["cheap", "expensive"]
    assert len(calls) > empty_calls
