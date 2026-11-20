import asyncio
from datetime import timedelta

import pytest
from aiokafka import AIOKafkaConsumer

from tandemetry.events.envelope import Event
from tandemetry.events.kafka import kafka_event_publisher
from tandemetry.settings import KafkaSettings

pytestmark = pytest.mark.integration

RECEIVE_TIMEOUT_SECONDS = 30


async def publish_and_receive(
    settings: KafkaSettings, events: list[Event]
) -> list[tuple[bytes, bytes, int]]:
    async with kafka_event_publisher(settings) as publisher:
        for event in events:
            await publisher.publish(event)
    consumer = AIOKafkaConsumer(
        settings.events_topic,
        bootstrap_servers=settings.bootstrap_servers,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        received: list[tuple[bytes, bytes, int]] = []
        async with asyncio.timeout(RECEIVE_TIMEOUT_SECONDS):
            async for message in consumer:
                received.append((message.key, message.value, message.partition))
                if len(received) == len(events):
                    break
        return received
    finally:
        await consumer.stop()


def test_published_event_round_trips_with_repo_id_key(
    kafka_settings: KafkaSettings, event: Event
) -> None:
    [(key, value, _)] = asyncio.run(publish_and_receive(kafka_settings, [event]))
    assert key == b"1296269"
    assert Event.model_validate_json(value) == event


def test_events_of_one_repository_share_a_partition(
    kafka_settings: KafkaSettings, event: Event
) -> None:
    later = Event.create(
        event.source,
        event.repo_id,
        event.repo,
        event.occurred_at + timedelta(minutes=1),
        event.payload,
    )
    received = asyncio.run(publish_and_receive(kafka_settings, [event, later, event]))
    assert [key for key, _, _ in received] == [b"1296269"] * 3
    assert len({partition for _, _, partition in received}) == 1
