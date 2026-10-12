from datetime import UTC, date, datetime

from app.core import clock


def test_today_is_singapore_date_even_while_utc_is_still_yesterday(monkeypatch) -> None:
    # 18:17 UTC on 11 Oct is 02:17 on 12 Oct in Singapore: a week planned then starts on the 12th.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 11, 18, 17, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", Clock)
    assert clock.today() == date(2026, 10, 12)
