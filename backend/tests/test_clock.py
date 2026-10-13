from datetime import UTC, date, datetime

from app.core import clock


def test_today_is_singapore_date_even_while_utc_is_still_yesterday(monkeypatch) -> None:
    # 18:17 UTC on 11 Oct is 02:17 on 12 Oct in Singapore: a week planned then starts on the 12th.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 11, 18, 17, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", Clock)
    monkeypatch.setattr(clock, "simulated", lambda: None)  # the real clock, whatever SIMULATED_TODAY says
    assert clock.today() == date(2026, 10, 12)


def test_a_simulated_day_keeps_the_time_of_day_and_a_simulated_moment_is_frozen(monkeypatch) -> None:
    monkeypatch.setattr(clock, "simulated", lambda: "2026-10-19")
    assert clock.today() == date(2026, 10, 19)
    monkeypatch.setattr(clock, "simulated", lambda: "2026-10-17T21:30")
    assert (clock.now().date(), clock.now().hour, clock.now().minute) == (date(2026, 10, 17), 21, 30)
