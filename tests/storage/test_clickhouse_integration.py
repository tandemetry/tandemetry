import argparse
import asyncio
from collections.abc import Sequence

import pytest

from tandemetry.cli import MigrateCommand
from tandemetry.events.envelope import Event
from tandemetry.settings import ClickHouseSettings
from tandemetry.storage.clickhouse import ClickHouseEventStore, clickhouse_client

pytestmark = pytest.mark.integration


async def migrate_twice_and_write_twice(
    settings: ClickHouseSettings, event: Event
) -> list[Sequence[object]]:
    await MigrateCommand(settings).run(argparse.Namespace())
    await MigrateCommand(settings).run(argparse.Namespace())
    async with clickhouse_client(settings) as client:
        store = ClickHouseEventStore(client)
        await store.write([event])
        await store.write([event])
        result = await client.query("SELECT event_id, repo_id, type, occurred_at FROM events FINAL")
        return list(result.result_rows)


def test_same_event_written_twice_is_stored_once(
    clickhouse_settings: ClickHouseSettings, event: Event
) -> None:
    rows = asyncio.run(migrate_twice_and_write_twice(clickhouse_settings, event))
    naive_utc = event.occurred_at.replace(tzinfo=None)
    assert rows == [(event.event_id, event.repo_id, "pull_request", naive_utc)]
