import argparse
import asyncio

import pytest
from aiokafka.admin import AIOKafkaAdminClient
from testcontainers.core.container import DockerContainer

from tandemetry.cli import MigrateCommand
from tandemetry.events.consumer import EventConsumer
from tandemetry.events.envelope import Event
from tandemetry.events.kafka import kafka_batch_source, kafka_event_publisher
from tandemetry.settings import ClickHouseSettings, KafkaSettings
from tandemetry.storage.clickhouse import clickhouse_client, clickhouse_event_store

pytestmark = pytest.mark.integration

CONSUME_TIMEOUT_SECONDS = 30


async def consume(kafka: KafkaSettings, clickhouse: ClickHouseSettings, expected: int) -> int:
    async with (
        clickhouse_event_store(clickhouse) as sink,
        kafka_batch_source(kafka) as source,
    ):
        consumer = EventConsumer(source, sink)
        written = 0
        async with asyncio.timeout(CONSUME_TIMEOUT_SECONDS):
            while written < expected:
                written += await consumer.run_once()
        return written


async def stored_events(clickhouse: ClickHouseSettings) -> int:
    async with clickhouse_client(clickhouse) as client:
        result = await client.query("SELECT count() FROM events FINAL")
        count: int = result.result_rows[0][0]
        return count


async def committed_offsets(kafka: KafkaSettings) -> int:
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka.bootstrap_servers)
    await admin.start()
    try:
        offsets = await admin.list_consumer_group_offsets(kafka.consumer_group)
        return sum(
            committed.offset
            for partition, committed in offsets.items()
            if partition.topic == kafka.events_topic
        )
    finally:
        await admin.close()


def reset_offsets_to_earliest(broker: DockerContainer, kafka: KafkaSettings) -> None:
    reset = broker.exec(
        [
            "/opt/kafka/bin/kafka-consumer-groups.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--group",
            kafka.consumer_group,
            "--topic",
            kafka.events_topic,
            "--reset-offsets",
            "--to-earliest",
            "--execute",
        ]
    )
    assert reset.exit_code == 0, reset.output


async def publish(kafka: KafkaSettings, event: Event) -> None:
    async with kafka_event_publisher(kafka) as publisher:
        await publisher.publish(event)


def test_redelivered_event_is_stored_once(
    kafka_broker: tuple[DockerContainer, str],
    kafka_settings: KafkaSettings,
    clickhouse_settings: ClickHouseSettings,
    event: Event,
) -> None:
    asyncio.run(MigrateCommand(clickhouse_settings).run(argparse.Namespace()))
    asyncio.run(publish(kafka_settings, event))

    assert asyncio.run(consume(kafka_settings, clickhouse_settings, expected=1)) == 1
    assert asyncio.run(stored_events(clickhouse_settings)) == 1
    assert asyncio.run(committed_offsets(kafka_settings)) == 1

    reset_offsets_to_earliest(kafka_broker[0], kafka_settings)

    assert asyncio.run(consume(kafka_settings, clickhouse_settings, expected=1)) == 1
    assert asyncio.run(stored_events(clickhouse_settings)) == 1
