from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Protocol

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from tandemetry.events.envelope import Event
from tandemetry.events.ports import Record
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


class ConsumedMessage(Protocol):
    @property
    def topic(self) -> str: ...
    @property
    def partition(self) -> int: ...
    @property
    def offset(self) -> int: ...
    @property
    def value(self) -> bytes | None: ...


class MessageFetcher(Protocol):
    async def getmany(
        self, *, timeout_ms: int, max_records: int
    ) -> Mapping[object, Sequence[ConsumedMessage]]: ...

    async def commit(self) -> None: ...


class KafkaBatchSource:
    """Batch source over a Kafka consumer group with manual offset commits."""

    def __init__(self, fetcher: MessageFetcher, timeout_ms: int, max_records: int) -> None:
        self._fetcher = fetcher
        self._timeout_ms = timeout_ms
        self._max_records = max_records

    async def next_batch(self) -> Sequence[Record]:
        batches = await self._fetcher.getmany(
            timeout_ms=self._timeout_ms, max_records=self._max_records
        )
        return [
            Record(message.topic, message.partition, message.offset, message.value or b"")
            for messages in batches.values()
            for message in messages
        ]

    async def commit(self) -> None:
        await self._fetcher.commit()


@asynccontextmanager
async def kafka_batch_source(settings: KafkaSettings) -> AsyncIterator[KafkaBatchSource]:
    """A batch source on the configured topic and consumer group, open for the block."""
    consumer = AIOKafkaConsumer(
        settings.events_topic,
        bootstrap_servers=settings.bootstrap_servers,
        group_id=settings.consumer_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    try:
        await consumer.start()
        yield KafkaBatchSource(consumer, settings.poll_timeout_ms, settings.max_batch_records)
    finally:
        await consumer.stop()
