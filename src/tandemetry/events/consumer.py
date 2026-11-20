import logging
from typing import NoReturn

from pydantic import ValidationError

from tandemetry.events.envelope import Event
from tandemetry.events.ports import BatchSource, EventSink, Record

logger = logging.getLogger(__name__)


class EventConsumer:
    """Moves events from a batch source to a sink, committing only after the sink succeeds."""

    def __init__(self, source: BatchSource, sink: EventSink) -> None:
        self._source = source
        self._sink = sink

    async def run(self) -> NoReturn:
        while True:
            await self.run_once()

    async def run_once(self) -> int:
        records = await self._source.next_batch()
        if not records:
            return 0
        events = [event for record in records if (event := self._decode(record)) is not None]
        await self._sink.write(events)
        await self._source.commit()
        return len(events)

    @staticmethod
    def _decode(record: Record) -> Event | None:
        try:
            return Event.model_validate_json(record.value)
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(map(str, problem['loc']))}: {problem['type']}"
                for problem in error.errors(
                    include_input=False, include_url=False, include_context=False
                )
            )
            logger.warning(
                "invalid event at %s[%d]@%d: %s",
                record.topic,
                record.partition,
                record.offset,
                problems,
            )
            return None
