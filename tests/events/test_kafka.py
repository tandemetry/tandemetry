import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tandemetry.events.kafka import ConsumedMessage, KafkaBatchSource
from tandemetry.events.ports import Record


@dataclass(frozen=True)
class Message:
    topic: str
    partition: int
    offset: int
    value: bytes | None


class FakeFetcher:
    def __init__(self, batches: Mapping[object, Sequence[ConsumedMessage]]) -> None:
        self._batches = batches
        self.requests: list[tuple[int, int]] = []

    async def getmany(
        self, *, timeout_ms: int, max_records: int
    ) -> Mapping[object, Sequence[ConsumedMessage]]:
        self.requests.append((timeout_ms, max_records))
        return self._batches

    async def commit(self) -> None:
        return None


def test_next_batch_flattens_partitions_and_maps_tombstones() -> None:
    fetcher = FakeFetcher(
        {
            0: [Message("events", 0, 5, b"a"), Message("events", 0, 6, None)],
            1: [Message("events", 1, 9, b"b")],
        }
    )
    records = asyncio.run(KafkaBatchSource(fetcher, timeout_ms=250, max_records=50).next_batch())
    assert records == [
        Record("events", 0, 5, b"a"),
        Record("events", 0, 6, b""),
        Record("events", 1, 9, b"b"),
    ]
    assert fetcher.requests == [(250, 50)]
