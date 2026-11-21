from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from tandemetry.events.kafka import (
    KafkaBatchSource,
    MessageSender,
    kafka_producer,
    kafka_topic_source,
)
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.settings import KafkaSettings


class KafkaRawWebhookPublisher:
    """Raw webhook publisher keyed by `repo_id`, so each repository's deliveries stay in order."""

    def __init__(self, sender: MessageSender, topic: str) -> None:
        self._sender = sender
        self._topic = topic

    async def publish(self, webhook: RawWebhook) -> None:
        await self._sender.send_and_wait(
            self._topic,
            value=webhook.model_dump_json().encode(),
            key=str(webhook.repo_id).encode(),
        )


@asynccontextmanager
async def kafka_raw_webhook_publisher(
    settings: KafkaSettings,
) -> AsyncIterator[KafkaRawWebhookPublisher]:
    """A raw webhook publisher to the configured raw topic, open for the block."""
    async with kafka_producer(settings) as producer:
        yield KafkaRawWebhookPublisher(producer, settings.raw_topic)


@asynccontextmanager
async def kafka_raw_webhook_source(settings: KafkaSettings) -> AsyncIterator[KafkaBatchSource]:
    """A batch source on the raw topic for the normalizer consumer group, open for the block."""
    async with kafka_topic_source(
        settings,
        settings.raw_topic,
        settings.normalizer_group,
        settings.normalizer_max_poll_interval_ms,
    ) as source:
        yield source
