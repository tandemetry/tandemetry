import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tandemetry.events.envelope import Event
from tandemetry.events.payloads import PullRequest
from tandemetry.storage.clickhouse import (
    EVENT_COLUMNS,
    EVENTS_TABLE,
    ClickHouseEventStore,
    ClickHouseMigrator,
    event_row,
)


class FakeExecutor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    async def command(self, cmd: str) -> object:
        self.commands.append(cmd)
        return None


class FakeInserter:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, list[Sequence[Any]], Sequence[str]]] = []

    async def insert(
        self, table: str, data: Sequence[Sequence[Any]], column_names: Sequence[str]
    ) -> object:
        self.inserts.append((table, list(data), column_names))
        return None


def test_store_writes_a_batch_in_one_insert(event: Event) -> None:
    inserter = FakeInserter()
    asyncio.run(ClickHouseEventStore(inserter).write([event, event, event]))
    assert inserter.inserts == [(EVENTS_TABLE, [event_row(event)] * 3, EVENT_COLUMNS)]


def test_store_skips_an_empty_batch() -> None:
    inserter = FakeInserter()
    asyncio.run(ClickHouseEventStore(inserter).write([]))
    assert inserter.inserts == []


def test_event_row_matches_columns(event: Event) -> None:
    row = dict(zip(EVENT_COLUMNS, event_row(event), strict=True))
    assert row["event_id"] == event.event_id
    assert row["source"] == "github"
    assert row["repo_id"] == 1296269
    assert row["repo"] == "acme/widgets"
    assert row["type"] == "pull_request"
    assert row["occurred_at"] == event.occurred_at


def test_event_row_payload_round_trips(event: Event) -> None:
    payload = dict(zip(EVENT_COLUMNS, event_row(event), strict=True))["payload"]
    assert isinstance(payload, str)
    assert PullRequest.model_validate_json(payload) == event.payload


def test_migrator_applies_sql_scripts_in_name_order(tmp_path: Path) -> None:
    (tmp_path / "0002_second.sql").write_text("SECOND")
    (tmp_path / "0001_first.sql").write_text("FIRST")
    (tmp_path / "README.md").write_text("not a migration")
    executor = FakeExecutor()

    applied = asyncio.run(ClickHouseMigrator(executor, tmp_path).apply())

    assert applied == ["0001_first.sql", "0002_second.sql"]
    assert executor.commands == ["FIRST", "SECOND"]


def test_migrator_ships_the_events_table() -> None:
    executor = FakeExecutor()
    applied = asyncio.run(ClickHouseMigrator(executor).apply())
    assert applied[0] == "0001_events.sql"
    assert "CREATE TABLE IF NOT EXISTS events" in executor.commands[0]
