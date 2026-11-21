import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

from pydantic import ValidationError

from tandemetry.events.envelope import Event
from tandemetry.events.ports import BatchSource, EventPublisher, Record
from tandemetry.events.validation import describe
from tandemetry.ingest.github.mapper import InvalidWebhookError
from tandemetry.ingest.github.normalizer import WebhookNormalizer
from tandemetry.ingest.github.ports import (
    GitHubNotFoundError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
)
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.transport import Clock, utc_now

logger = logging.getLogger(__name__)

MIN_RATE_LIMIT_WAIT_S = 1.0
MAX_BACKOFF_EXPONENT = 32

Sleep = Callable[[float], Awaitable[None]]


class NormalizerStalledError(Exception):
    """A batch could not be normalized within its deadline; it is left uncommitted."""


@dataclass(frozen=True)
class RetryPolicy:
    initial_s: float
    max_s: float
    rate_limit_max_wait_s: float
    batch_deadline_s: float

    def backoff(self, attempt: int) -> float:
        return min(self.initial_s * 2.0 ** min(attempt, MAX_BACKOFF_EXPONENT), self.max_s)

    def rate_limit_wait(self, seconds_until_reset: float) -> float:
        return min(max(seconds_until_reset, MIN_RATE_LIMIT_WAIT_S), self.rate_limit_max_wait_s)


class NormalizerWorker:
    """Normalizes raw deliveries into events and commits a batch only after all are published."""

    def __init__(
        self,
        source: BatchSource,
        normalizer: WebhookNormalizer,
        publisher: EventPublisher,
        retry: RetryPolicy,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = utc_now,
    ) -> None:
        self._source = source
        self._normalizer = normalizer
        self._publisher = publisher
        self._retry = retry
        self._sleep = sleep
        self._clock = clock

    async def run(self) -> NoReturn:
        while True:
            await self.run_once()

    async def run_once(self) -> int:
        records = await self._source.next_batch()
        if not records:
            return 0
        deadline = self._clock() + timedelta(seconds=self._retry.batch_deadline_s)
        published = 0
        for record in records:
            for event in await self._normalize(record, deadline):
                await self._publisher.publish(event)
                published += 1
        await self._source.commit()
        return published

    async def _normalize(self, record: Record, deadline: datetime) -> list[Event]:
        position = f"{record.topic}[{record.partition}]@{record.offset}"
        try:
            raw = RawWebhook.model_validate_json(record.value)
        except ValidationError as error:
            logger.warning("invalid raw webhook at %s: %s", position, describe(error))
            return []
        attempt = 0
        while True:
            try:
                return await self._normalizer.normalize(raw)
            except (InvalidWebhookError, GitHubNotFoundError) as error:
                logger.warning("skipped delivery %s at %s: %s", raw.delivery_id, position, error)
                return []
            except GitHubRateLimitedError as error:
                wait = self._retry.rate_limit_wait((error.retry_at - self._clock()).total_seconds())
                logger.warning("GitHub rate limit, waiting %.0fs", wait)
                await self._wait(wait, deadline)
            except GitHubUnavailableError as error:
                wait = self._retry.backoff(attempt)
                attempt += 1
                logger.warning("GitHub unavailable (%s), retrying in %.0fs", error, wait)
                await self._wait(wait, deadline)

    async def _wait(self, seconds: float, deadline: datetime) -> None:
        if self._clock() + timedelta(seconds=seconds) > deadline:
            raise NormalizerStalledError(
                f"batch not normalized within {self._retry.batch_deadline_s:.0f}s"
            )
        await self._sleep(seconds)
