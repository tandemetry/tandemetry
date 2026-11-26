import asyncio
import socket
import uuid
from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy, LogMessageWaitStrategy

from tandemetry.events.envelope import Event
from tandemetry.events.sample import SAMPLE_EVENT
from tandemetry.settings import ClickHouseSettings, KafkaSettings
from tandemetry.storage.clickhouse import clickhouse_client

CLICKHOUSE_IMAGE = "clickhouse/clickhouse-server:25.8.33"
CLICKHOUSE_HTTP_PORT = 8123
KAFKA_IMAGE = "apache/kafka:4.4.0"
KAFKA_HOST_LISTENER_PORT = 29092
EVENTS_TOPIC_PARTITIONS = 3


@pytest.fixture
def event() -> Event:
    return SAMPLE_EVENT


@pytest.fixture(scope="session")
def clickhouse_server() -> Iterator[ClickHouseSettings]:
    settings = ClickHouseSettings(username="tandemetry", password=SecretStr("test"))
    container = (
        DockerContainer(CLICKHOUSE_IMAGE)
        .with_exposed_ports(CLICKHOUSE_HTTP_PORT)
        .with_envs(
            CLICKHOUSE_USER=settings.username,
            CLICKHOUSE_PASSWORD=settings.password.get_secret_value(),
            CLICKHOUSE_DB=settings.database,
        )
        .waiting_for(HttpWaitStrategy(CLICKHOUSE_HTTP_PORT, "/ping"))
    )
    with container:
        yield settings.model_copy(
            update={
                "host": container.get_container_host_ip(),
                "port": container.get_exposed_port(CLICKHOUSE_HTTP_PORT),
            }
        )


async def create_database(server: ClickHouseSettings, database: str) -> None:
    async with clickhouse_client(server) as client:
        await client.command(f"CREATE DATABASE {database}")


@pytest.fixture
def clickhouse_settings(clickhouse_server: ClickHouseSettings) -> ClickHouseSettings:
    database = f"test_{uuid.uuid4().hex}"
    asyncio.run(create_database(clickhouse_server, database))
    return clickhouse_server.model_copy(update={"database": database})


def free_host_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def kafka_broker() -> Iterator[tuple[DockerContainer, str]]:
    host_port = free_host_port()
    container = (
        DockerContainer(KAFKA_IMAGE)
        .with_bind_ports(KAFKA_HOST_LISTENER_PORT, host_port)
        .with_envs(
            KAFKA_NODE_ID="1",
            KAFKA_PROCESS_ROLES="broker,controller",
            KAFKA_LISTENERS=f"PLAINTEXT://:9092,CONTROLLER://:9093,HOST://:{KAFKA_HOST_LISTENER_PORT}",
            KAFKA_ADVERTISED_LISTENERS=f"PLAINTEXT://localhost:9092,HOST://localhost:{host_port}",
            KAFKA_LISTENER_SECURITY_PROTOCOL_MAP="CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,HOST:PLAINTEXT",
            KAFKA_CONTROLLER_LISTENER_NAMES="CONTROLLER",
            KAFKA_CONTROLLER_QUORUM_VOTERS="1@localhost:9093",
            KAFKA_INTER_BROKER_LISTENER_NAME="PLAINTEXT",
            KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR="1",
            KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR="1",
            KAFKA_TRANSACTION_STATE_LOG_MIN_ISR="1",
            KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS="0",
        )
        .waiting_for(LogMessageWaitStrategy("Kafka Server started"))
    )
    with container:
        yield container, f"localhost:{host_port}"


@pytest.fixture
def kafka_settings(kafka_broker: tuple[DockerContainer, str]) -> KafkaSettings:
    container, bootstrap_servers = kafka_broker
    topic = f"events-{uuid.uuid4().hex}"
    created = container.exec(
        [
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--create",
            "--topic",
            topic,
            "--partitions",
            str(EVENTS_TOPIC_PARTITIONS),
        ]
    )
    assert created.exit_code == 0, created.output
    return KafkaSettings(
        bootstrap_servers=bootstrap_servers,
        events_topic=topic,
        consumer_group=f"group-{uuid.uuid4().hex}",
    )
