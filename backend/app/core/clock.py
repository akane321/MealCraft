"""Now and today where the households live, not on the server's clock.

The containers run in UTC, so before 08:00 in Singapore `date.today()` is still yesterday: a week planned
then started on a day that had already passed.

Outside production, SIMULATED_TODAY sets the date the product takes as today ("2026-10-19", keeping the real
time of day) or the moment ("2026-10-19T21:30", frozen), so a weekend, a late evening or a week's last day can
be reproduced in debugging and demos.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

SINGAPORE = ZoneInfo("Asia/Singapore")
_frozen_now: ContextVar[datetime | None] = ContextVar("mealcraft_frozen_now", default=None)


@contextmanager
def frozen(at: datetime) -> Iterator[None]:
    """Inject an aware, fixed product clock for an isolated run; restore even on failure.

    This is a Python-only seam, not an HTTP option or a process-wide settings edit.
    Context-local values keep concurrent evaluation conversations from changing each other.
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("The injected clock must have a timezone")
    token = _frozen_now.set(at.astimezone(SINGAPORE))
    try:
        yield
    finally:
        _frozen_now.reset(token)


def simulated() -> str | None:
    """The simulated now, as configured, or None when the real clock is used."""
    settings = get_settings()
    if not settings.simulated_today or settings.environment.casefold() not in {"development", "test"}:
        return None
    return settings.simulated_today


def now() -> datetime:
    injected = _frozen_now.get()
    if injected is not None:
        return injected
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
