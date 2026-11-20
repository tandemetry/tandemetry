from collections.abc import Sequence
from typing import Protocol

from tandemetry.events.envelope import Event


class EventSink(Protocol):
    async def write(self, events: Sequence[Event]) -> None:
        """Persist events; writing an already stored event must be harmless."""


class EventPublisher(Protocol):
    async def publish(self, event: Event) -> None:
        """Hand an event to the stream; publishing it again is allowed, sinks dedupe by id."""
