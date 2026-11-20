from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from tandemetry.events.envelope import Event


class EventSink(Protocol):
    async def write(self, events: Sequence[Event]) -> None:
        """Persist events; writing an already stored event must be harmless."""


class EventPublisher(Protocol):
    async def publish(self, event: Event) -> None:
        """Hand an event to the stream; publishing it again is allowed, sinks dedupe by id."""


@dataclass(frozen=True)
class Record:
    topic: str
    partition: int
    offset: int
    value: bytes


class BatchSource(Protocol):
    async def next_batch(self) -> Sequence[Record]:
        """The next records of the stream; empty when none arrived in time."""

    async def commit(self) -> None:
        """Mark every record returned so far as processed."""
