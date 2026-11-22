import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from tandemetry.ingest.github.ports import GitHubRateLimitedError, GitHubUnavailableError
from tandemetry.ingest.github.transport import Clock, utc_now

logger = logging.getLogger(__name__)

MIN_RATE_LIMIT_WAIT_S = 1.0
MAX_BACKOFF_EXPONENT = 32

Sleep = Callable[[float], Awaitable[None]]


class GitHubStalledError(Exception):
    """GitHub requests did not succeed within their deadline."""


@dataclass(frozen=True)
class RetryPolicy:
    """How long to back off, wait for a rate limit reset and keep trying."""

    initial_s: float
    max_s: float
    rate_limit_max_wait_s: float
    batch_deadline_s: float

    def backoff(self, attempt: int) -> float:
        """Seconds to wait before the retry after `attempt` transient failures."""
        return min(self.initial_s * 2.0 ** min(attempt, MAX_BACKOFF_EXPONENT), self.max_s)

    def rate_limit_wait(self, seconds_until_reset: float) -> float:
        """Seconds to wait for a rate limit reset, clamped to the policy's bounds."""
        return min(max(seconds_until_reset, MIN_RATE_LIMIT_WAIT_S), self.rate_limit_max_wait_s)


class GitHubRetry:
    """Repeats GitHub requests through rate limits and transient failures until a deadline."""

    def __init__(
        self, policy: RetryPolicy, sleep: Sleep = asyncio.sleep, clock: Clock = utc_now
    ) -> None:
        self._policy = policy
        self._sleep = sleep
        self._clock = clock

    def deadline(self) -> datetime:
        """The moment a unit of work started now must be done by."""
        return self._clock() + timedelta(seconds=self._policy.batch_deadline_s)

    async def call[Result](
        self, request: Callable[[], Awaitable[Result]], deadline: datetime
    ) -> Result:
        """The result of `request`, retried until it succeeds or the deadline would pass."""
        attempt = 0
        while True:
            try:
                return await request()
            except GitHubRateLimitedError as error:
                until_reset = (error.retry_at - self._clock()).total_seconds()
                wait = self._policy.rate_limit_wait(until_reset)
                logger.warning("GitHub rate limit, waiting %.0fs", wait)
                await self._wait(wait, deadline)
            except GitHubUnavailableError as error:
                wait = self._policy.backoff(attempt)
                attempt += 1
                logger.warning("GitHub unavailable (%s), retrying in %.0fs", error, wait)
                await self._wait(wait, deadline)

    async def _wait(self, seconds: float, deadline: datetime) -> None:
        if self._clock() + timedelta(seconds=seconds) > deadline:
            raise GitHubStalledError(
                f"GitHub requests not done within {self._policy.batch_deadline_s:.0f}s"
            )
        await self._sleep(seconds)
