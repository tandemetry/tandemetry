import asyncio
import logging
from collections.abc import Sequence

import pytest

from tandemetry.events.consumer import EventConsumer
from tandemetry.events.envelope import Event
from tandemetry.events.ports import Record

INVALID_PAYLOAD = b'{"event_id": "secret-looking-payload"}'


class SourceExhaustedError(Exception):
    pass


class FakeBatchSource:
    def __init__(self, *batches: Sequence[Record]) -> None:
        self._batches = list(batches)
        self.commits = 0

    async def next_batch(self) -> Sequence[Record]:
        if not self._batches:
            raise SourceExhaustedError
        return self._batches.pop(0)

    async def commit(self) -> None:
        self.commits += 1


class FakeSink:
    def __init__(self, failure: Exception | None = None) -> None:
        self.writes: list[list[Event]] = []
        self._failure = failure

    async def write(self, events: Sequence[Event]) -> None:
        if self._failure is not None:
            raise self._failure
        self.writes.append(list(events))


def record(value: bytes, offset: int = 0) -> Record:
    return Record("events.normalized", 2, offset, value)


def valid(event: Event, offset: int = 0) -> Record:
    return record(event.model_dump_json().encode(), offset)


def test_valid_batch_is_written_then_committed(event: Event) -> None:
    source, sink = FakeBatchSource([valid(event), valid(event, 1)]), FakeSink()
    written = asyncio.run(EventConsumer(source, sink).run_once())
    assert written == 2
    assert sink.writes == [[event, event]]
    assert source.commits == 1


def test_invalid_message_is_logged_and_skipped(
    event: Event, caplog: pytest.LogCaptureFixture
) -> None:
    source, sink = FakeBatchSource([valid(event), record(INVALID_PAYLOAD, 7)]), FakeSink()
    with caplog.at_level(logging.WARNING):
        written = asyncio.run(EventConsumer(source, sink).run_once())
    assert written == 1
    assert sink.writes == [[event]]
    assert source.commits == 1
    assert "invalid event at events.normalized[2]@7" in caplog.text
    assert "secret-looking-payload" not in caplog.text


def test_sink_failure_propagates_without_commit(event: Event) -> None:
    source, sink = FakeBatchSource([valid(event)]), FakeSink(failure=ConnectionError("down"))
    with pytest.raises(ConnectionError):
        asyncio.run(EventConsumer(source, sink).run_once())
    assert source.commits == 0


def test_batch_of_only_invalid_messages_is_committed() -> None:
    source, sink = FakeBatchSource([record(b"not json"), record(b"")]), FakeSink()
    written = asyncio.run(EventConsumer(source, sink).run_once())
    assert written == 0
    assert sink.writes == [[]]
    assert source.commits == 1


def test_empty_batch_is_not_committed() -> None:
    source, sink = FakeBatchSource([]), FakeSink()
    assert asyncio.run(EventConsumer(source, sink).run_once()) == 0
    assert sink.writes == []
    assert source.commits == 0


def test_run_processes_batches_until_the_source_fails(event: Event) -> None:
    source, sink = FakeBatchSource([valid(event)], [], [valid(event, 1)]), FakeSink()
    with pytest.raises(SourceExhaustedError):
        asyncio.run(EventConsumer(source, sink).run())
    assert sink.writes == [[event], [event]]
    assert source.commits == 2
