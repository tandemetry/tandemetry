from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from aiokafka import AIOKafkaProducer

from tandemetry.events.envelope import Event
from tandemetry.settings import KafkaSettings


class MessageSender(Protocol):
    async def send_and_wait(self, topic: str, value: bytes, key: bytes) -> object: ...


class KafkaEventPublisher:
    """Event publisher keyed by `repo_id`, so each repository's events stay in order."""

    def __init__(self, sender: MessageSender, topic: str) -> None:
        self._sender = sender
        self._topic = topic

    async def publish(self, event: Event) -> None:
        await self._sender.send_and_wait(
            self._topic,
            value=event.model_dump_json().encode(),
            key=str(event.repo_id).encode(),
        )


@asynccontextmanager
async def kafka_event_publisher(settings: KafkaSettings) -> AsyncIterator[KafkaEventPublisher]:
    """An event publisher to the configured Kafka topic, open for the duration of the block."""
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.bootstrap_servers,
        acks="all",
        enable_idempotence=True,
    )
    try:
        await producer.start()
        yield KafkaEventPublisher(producer, settings.events_topic)
    finally:
        await producer.stop()
