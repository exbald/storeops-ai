from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime:
        """Return current datetime in UTC."""
        ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)
