from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class StartedClock:
    """Starts at a fixed moment, then runs in real time. For the browser tests: order dates and return
    windows hold on any day the suite runs, while timers still move."""

    def __init__(self, start: datetime) -> None:
        self._offset = start - datetime.now(timezone.utc)

    def now(self) -> datetime:
        return datetime.now(timezone.utc) + self._offset
