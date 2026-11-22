import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from tandemetry.ingest.github.ports import (
    GitHubApiError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
)
from tandemetry.ingest.github.retry import GitHubRetry, GitHubStalledError, RetryPolicy

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
POLICY = RetryPolicy(initial_s=1.0, max_s=4.0, rate_limit_max_wait_s=600.0, batch_deadline_s=900.0)


class AdvancingClock:
    def __init__(self) -> None:
        self.now = NOW
        self.waits: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += timedelta(seconds=seconds)


class ScriptedRequest:
    def __init__(self, *failures: GitHubApiError) -> None:
        self._failures = list(failures)
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return "done"


def call(request: ScriptedRequest, clock: AdvancingClock) -> str:
    retry = GitHubRetry(POLICY, clock.sleep, clock)
    return asyncio.run(retry.call(request, retry.deadline()))


def test_success_returns_the_result_without_waiting() -> None:
    clock, request = AdvancingClock(), ScriptedRequest()
    assert (call(request, clock), request.calls, clock.waits) == ("done", 1, [])


def test_rate_limit_is_waited_out_until_reset() -> None:
    clock = AdvancingClock()
    request = ScriptedRequest(GitHubRateLimitedError(NOW + timedelta(seconds=90)))
    assert (call(request, clock), request.calls, clock.waits) == ("done", 2, [90.0])


def test_transient_failures_back_off_exponentially_up_to_the_cap() -> None:
    clock = AdvancingClock()
    request = ScriptedRequest(*(GitHubUnavailableError("HTTP 502") for _ in range(4)))
    assert (call(request, clock), clock.waits) == ("done", [1.0, 2.0, 4.0, 4.0])


def test_other_failures_are_not_retried() -> None:
    clock, request = AdvancingClock(), ScriptedRequest(GitHubApiError("HTTP 401"))
    with pytest.raises(GitHubApiError, match="401"):
        call(request, clock)
    assert (request.calls, clock.waits) == (1, [])


def test_request_that_would_outlast_the_deadline_stalls() -> None:
    clock = AdvancingClock()
    request = ScriptedRequest(*(GitHubRateLimitedError(NOW + timedelta(days=1)) for _ in range(3)))
    with pytest.raises(GitHubStalledError, match="900s"):
        call(request, clock)
    assert clock.waits == [600.0]


@pytest.mark.parametrize(("until_reset", "wait"), [(-5.0, 1.0), (30.0, 30.0), (7200.0, 600.0)])
def test_rate_limit_wait_is_clamped(until_reset: float, wait: float) -> None:
    assert POLICY.rate_limit_wait(until_reset) == wait


def test_backoff_stays_finite_after_many_attempts() -> None:
    assert POLICY.backoff(10_000) == POLICY.max_s
