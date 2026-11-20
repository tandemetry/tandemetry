from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any, Protocol
from uuid import UUID

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from tandemetry.events.envelope import Event
from tandemetry.settings import ClickHouseSettings

EVENTS_TABLE = "events"
EVENT_COLUMNS = ("event_id", "source", "repo_id", "repo", "type", "occurred_at", "payload")
MIGRATIONS = files("tandemetry.storage") / "clickhouse_migrations"

EventRow = tuple[UUID, str, int, str, str, datetime, str]


def event_row(event: Event) -> EventRow:
    """The `events` table row for an event, in `EVENT_COLUMNS` order."""
    return (
        event.event_id,
        event.source.value,
        event.repo_id,
        event.repo,
        event.payload.type,
        event.occurred_at,
        event.payload.model_dump_json(),
    )


@asynccontextmanager
async def clickhouse_client(settings: ClickHouseSettings) -> AsyncIterator[AsyncClient]:
    """An async ClickHouse HTTP client, closed on exit."""
    client = await clickhouse_connect.get_async_client(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password.get_secret_value(),
        database=settings.database,
    )
    try:
        yield client
    finally:
        await client.close()


class RowInserter(Protocol):
    async def insert(
        self, table: str, data: Sequence[Sequence[Any]], column_names: Sequence[str]
    ) -> object: ...


class ClickHouseEventStore:
    """Event sink writing each batch to the `events` table in one insert."""

    def __init__(self, client: RowInserter) -> None:
        self._client = client

    async def write(self, events: Sequence[Event]) -> None:
        if not events:
            return
        rows = [event_row(event) for event in events]
        await self._client.insert(EVENTS_TABLE, rows, column_names=EVENT_COLUMNS)


class SqlExecutor(Protocol):
    async def command(self, cmd: str) -> object: ...


class ClickHouseMigrator:
    """Applies migration files, one idempotent DDL statement each, in file name order."""

    def __init__(self, executor: SqlExecutor, scripts: Traversable = MIGRATIONS) -> None:
        self._executor = executor
        self._scripts = scripts

    async def apply(self) -> list[str]:
        statements = {
            script.name: script.read_text()
            for script in self._scripts.iterdir()
            if script.name.endswith(".sql")
        }
        for name in sorted(statements):
            await self._executor.command(statements[name])
        return sorted(statements)
