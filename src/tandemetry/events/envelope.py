from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, Field, PositiveInt, field_validator, model_validator

from tandemetry.events.payloads import (
    CheckRun,
    Commit,
    DomainModel,
    Merge,
    Payload,
    PullRequest,
    Revert,
    Review,
)

EVENT_ID_NAMESPACE = uuid5(NAMESPACE_URL, "https://github.com/tandemetry/tandemetry/events/v1")

EventPayload = Annotated[
    PullRequest | Commit | Review | CheckRun | Merge | Revert,
    Field(discriminator="type"),
]


class Source(StrEnum):
    GITHUB = "github"


def derive_event_id(source: Source, repo_id: int, occurred_at: datetime, payload: Payload) -> UUID:
    """Deterministic id of a source fact, shared by webhooks and backfill."""
    parts = [
        source,
        str(repo_id),
        payload.type,
        payload.natural_key,
        occurred_at.astimezone(UTC).isoformat(),
    ]
    return uuid5(EVENT_ID_NAMESPACE, "|".join(parts))


class Event(DomainModel):
    """A platform fact, built only via `create`; `occurred_at` is the platform's timestamp."""

    event_id: UUID
    source: Source
    repo_id: PositiveInt
    repo: str = Field(pattern=r"^[^/\s]+(/[^/\s]+)+$")
    occurred_at: AwareDatetime
    payload: EventPayload

    @classmethod
    def create(
        cls,
        source: Source,
        repo_id: int,
        repo: str,
        occurred_at: datetime,
        payload: EventPayload,
    ) -> Self:
        """Build an event with its derived `event_id`."""
        return cls(
            event_id=derive_event_id(source, repo_id, occurred_at, payload),
            source=source,
            repo_id=repo_id,
            repo=repo,
            occurred_at=occurred_at,
            payload=payload,
        )

    @field_validator("occurred_at")
    @classmethod
    def _in_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _event_id_matches_fact(self) -> Self:
        expected = derive_event_id(self.source, self.repo_id, self.occurred_at, self.payload)
        if self.event_id != expected:
            raise ValueError(
                f"event_id {self.event_id} does not match the fact; expected {expected}"
            )
        return self
