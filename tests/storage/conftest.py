from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from tandemetry.events.envelope import Event, Source
from tandemetry.events.payloads import PullRequest, PullRequestAction
from tandemetry.settings import ClickHouseSettings

CLICKHOUSE_IMAGE = "clickhouse/clickhouse-server:25.8.33"
CLICKHOUSE_HTTP_PORT = 8123


@pytest.fixture
def event() -> Event:
    pull_request = PullRequest(
        number=7,
        action=PullRequestAction.OPENED,
        author="copilot-swe-agent[bot]",
        body="Generated with Claude Code",
        head_branch="codex/fix-login",
        labels=("ai-generated",),
    )
    occurred_at = datetime(2026, 11, 13, 10, 0, 0, 123456, tzinfo=UTC)
    return Event.create(Source.GITHUB, 1296269, "acme/widgets", occurred_at, pull_request)


@pytest.fixture(scope="session")
def clickhouse_settings() -> Iterator[ClickHouseSettings]:
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
