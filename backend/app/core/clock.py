"""Now and today where the households live, not on the server's clock.

The containers run in UTC, so before 08:00 in Singapore `date.today()` is still yesterday: a week planned
then started on a day that had already passed.

Outside production, SIMULATED_TODAY sets the date the product takes as today ("2026-10-19", keeping the real
time of day) or the moment ("2026-10-19T21:30", frozen), so a weekend, a late evening or a week's last day can
be reproduced in debugging and demos.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

SINGAPORE = ZoneInfo("Asia/Singapore")


def simulated() -> str | None:
    """The simulated now, as configured, or None when the real clock is used."""
    settings = get_settings()
    if not settings.simulated_today or settings.environment.casefold() not in {"development", "test"}:
        return None
    return settings.simulated_today


def now() -> datetime:
    real = datetime.now(SINGAPORE)
    value = simulated()
    if value is None:
        return real
    if "T" in value:
        return datetime.fromisoformat(value).replace(tzinfo=SINGAPORE)
    day = date.fromisoformat(value)
    return real.replace(year=day.year, month=day.month, day=day.day)


def today() -> date:
    return now().date()
