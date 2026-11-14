from __future__ import annotations

from custom_components.ttlock_ble.connection_quality import (
    CONNECTION_ATTEMPT_WINDOW,
    TtlockBleConnectionQuality,
)


def test_nothing_is_known_before_any_attempt() -> None:
    quality = TtlockBleConnectionQuality()
    assert quality.success_rate is None
    assert quality.last_connect_seconds is None
    assert quality.attempts == 0
    assert quality.failures == 0


def test_rate_counts_successes_and_failures() -> None:
    quality = TtlockBleConnectionQuality()
    quality.record_success(1.5)
    quality.record_failure()
    quality.record_success(2.0)
    quality.record_failure()
    assert quality.attempts == 4
    assert quality.failures == 2
    assert quality.success_rate == 50


def test_connect_time_is_the_last_success() -> None:
    quality = TtlockBleConnectionQuality()
    quality.record_success(1.5)
    quality.record_success(0.75)
    quality.record_failure()
    assert quality.last_connect_seconds == 0.75


def test_only_the_most_recent_attempts_count() -> None:
    """A lock that stopped failing recovers once the old failures leave the window."""
    quality = TtlockBleConnectionQuality()
    for _ in range(CONNECTION_ATTEMPT_WINDOW):
        quality.record_failure()
    for _ in range(CONNECTION_ATTEMPT_WINDOW):
        quality.record_success(1.0)
    assert quality.attempts == CONNECTION_ATTEMPT_WINDOW
    assert quality.success_rate == 100
