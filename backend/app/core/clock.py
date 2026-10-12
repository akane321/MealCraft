"""Today's date where the households live, not on the server's clock.

The containers run in UTC, so before 08:00 in Singapore `date.today()` is still yesterday: a week planned
then started on a day that had already passed.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

SINGAPORE = ZoneInfo("Asia/Singapore")


def today() -> date:
    return datetime.now(SINGAPORE).date()
