import asyncio
import uuid
from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from tandemetry.events.envelope import Event
from tandemetry.events.sample import SAMPLE_EVENT
from tandemetry.settings import ClickHouseSettings
from tandemetry.storage.clickhouse import clickhouse_client

CLICKHOUSE_IMAGE = "clickhouse/clickhouse-server:25.8.33"
CLICKHOUSE_HTTP_PORT = 8123


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
