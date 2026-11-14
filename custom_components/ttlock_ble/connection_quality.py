"""How well the recent BLE session attempts with one lock went."""

from __future__ import annotations

from collections import deque

# Long enough that one unlucky attempt does not halve the rate, short
# enough that a lock moved closer to a proxy recovers within a day of
# ordinary use.
CONNECTION_ATTEMPT_WINDOW = 20


class TtlockBleConnectionQuality:
    """
    Outcome of the most recent BLE session attempts with one lock.

    Only attempts that reached the radio are counted: a lock no scanner
    has heard recently is never dialled, and its absence is what the
    last-seen sensor reports. What is left measures the link itself —
    how often a session that was tried came up, and how long it took.

    Kept in memory only. A restart says nothing about the link, so the
    readings start over rather than carrying a rate measured before it.
    """

    def __init__(self, window: int = CONNECTION_ATTEMPT_WINDOW) -> None:
        """Start with no attempts recorded."""
        self._outcomes: deque[bool] = deque(maxlen=window)
        self._last_connect_seconds: float | None = None

    @property
    def attempts(self) -> int:
        """Return how many attempts the window holds."""
        return len(self._outcomes)

    @property
    def failures(self) -> int:
        """Return how many attempts in the window failed."""
        return self._outcomes.count(False)

    @property
    def success_rate(self) -> float | None:
        """Return the share of attempts in the window that connected, in percent."""
        if not self._outcomes:
            return None
        return 100 * (self.attempts - self.failures) / self.attempts

    @property
    def last_connect_seconds(self) -> float | None:
        """Return how long the last successful session took to come up."""
        return self._last_connect_seconds

    def record_success(self, elapsed_seconds: float) -> None:
        """Record an attempt that opened a session after `elapsed_seconds`."""
        self._outcomes.append(True)
        self._last_connect_seconds = elapsed_seconds

    def record_failure(self) -> None:
        """Record an attempt that did not open a session."""
        self._outcomes.append(False)
