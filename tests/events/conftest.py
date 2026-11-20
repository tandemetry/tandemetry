import socket
import uuid
from collections.abc import Iterator

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from tandemetry.settings import KafkaSettings

KAFKA_IMAGE = "apache/kafka:4.4.0"
KAFKA_HOST_LISTENER_PORT = 29092
EVENTS_TOPIC_PARTITIONS = 3


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
