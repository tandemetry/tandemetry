import logging
from datetime import datetime
from functools import partial
from typing import NoReturn

from pydantic import ValidationError

from tandemetry.events.envelope import Event
from tandemetry.events.ports import BatchSource, EventPublisher, Record
from tandemetry.events.validation import describe
from tandemetry.ingest.github.mapper import InvalidWebhookError
from tandemetry.ingest.github.normalizer import WebhookNormalizer
from tandemetry.ingest.github.ports import GitHubNotFoundError
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.retry import GitHubRetry

logger = logging.getLogger(__name__)


class NormalizerWorker:
    """Normalizes raw deliveries into events and commits a batch only after all are published."""

    def __init__(
        self,
        source: BatchSource,
        normalizer: WebhookNormalizer,
        publisher: EventPublisher,
        retry: GitHubRetry,
    ) -> None:
        self._source = source
        self._normalizer = normalizer
        self._publisher = publisher
        self._retry = retry

    async def run(self) -> NoReturn:
        while True:
            await self.run_once()

    async def run_once(self) -> int:
        records = await self._source.next_batch()
        if not records:
            return 0
        deadline = self._retry.deadline()
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
        try:
            return await self._retry.call(partial(self._normalizer.normalize, raw), deadline)
        except (InvalidWebhookError, GitHubNotFoundError) as error:
            logger.warning("skipped delivery %s at %s: %s", raw.delivery_id, position, error)
            return []
