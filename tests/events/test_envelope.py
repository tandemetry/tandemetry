import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from tandemetry.events.envelope import Event, EventPayload, Source
from tandemetry.events.payloads import (
    CheckConclusion,
    CheckRun,
    Commit,
    FileChange,
    Merge,
    PullRequest,
    PullRequestAction,
    Revert,
    Review,
)

REPO = "acme/widgets"
SHA = "a" * 40
OTHER_SHA = "b" * 40
OCCURRED_AT = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)

PULL_REQUEST = PullRequest(
    number=7,
    action=PullRequestAction.OPENED,
    author="copilot-swe-agent[bot]",
    body="Generated with Claude Code",
    head_branch="codex/fix-login",
    labels=("ai-generated",),
)
PAYLOADS: list[EventPayload] = [
    PULL_REQUEST,
    Commit(
        sha=SHA,
        pull_request=7,
        author_login="octocat",
        author_email="octocat@example.com",
        message="fix: login\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
    ),
    Review(review_id=11, pull_request=7, reviewer="octocat"),
    CheckRun(check_run_id=13, name="ci", head_sha=SHA, conclusion=CheckConclusion.FAILURE),
    Merge(
        pull_request=7,
        merge_commit_sha=SHA,
        files=(FileChange(path="src/login.py", additions=3, deletions=1),),
    ),
    Revert(sha=OTHER_SHA, reverted_shas=(SHA,), reverted_pull_request=None),
]


def event(
    payload: EventPayload = PULL_REQUEST, repo: str = REPO, occurred_at: datetime = OCCURRED_AT
) -> Event:
    return Event.create(Source.GITHUB, repo, occurred_at, payload)


def wire(**overrides: object) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(event().model_dump_json())
    data.update(overrides)
    return data


@pytest.mark.parametrize("payload", PAYLOADS, ids=lambda payload: payload.type)
def test_event_round_trips_through_json(payload: EventPayload) -> None:
    original = event(payload)

    restored = Event.model_validate_json(original.model_dump_json())

    assert restored == original
    assert type(restored.payload) is type(payload)


def test_event_id_is_deterministic() -> None:
    assert event().event_id == event().event_id


def test_event_id_ignores_timezone_offset() -> None:
    kyiv = OCCURRED_AT.astimezone(timezone(timedelta(hours=2)))

    shifted = event(occurred_at=kyiv)

    assert shifted.event_id == event().event_id
    assert shifted.occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "other",
    [
        event(repo="acme/gadgets"),
        event(occurred_at=OCCURRED_AT + timedelta(seconds=1)),
        event(PULL_REQUEST.model_copy(update={"action": PullRequestAction.CLOSED})),
    ],
    ids=["repo", "occurred_at", "action"],
)
def test_event_id_differs_per_fact(other: Event) -> None:
    assert other.event_id != event().event_id


def test_event_id_differs_per_type_with_same_key() -> None:
    review = Review(review_id=13, pull_request=7, reviewer="octocat")
    check_run = CheckRun(
        check_run_id=13, name="ci", head_sha=SHA, conclusion=CheckConclusion.SUCCESS
    )

    assert review.natural_key == check_run.natural_key
    assert event(review).event_id != event(check_run).event_id


def test_event_id_matches_published_recipe() -> None:
    assert event().event_id == UUID("fcfcfa07-ed66-5088-b1ee-2a86bedc17d2")


def test_mismatched_event_id_is_rejected() -> None:
    tampered = wire(event_id="00000000-0000-0000-0000-000000000000")

    with pytest.raises(ValidationError, match="does not match"):
        Event.model_validate(tampered)


def test_events_are_immutable() -> None:
    built = event()

    with pytest.raises(ValidationError):
        built.repo = "acme/gadgets"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        built.payload.author = "someone"  # type: ignore[misc,union-attr]


def payload_with(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = wire()["payload"]
    payload.update(overrides)
    return wire(payload=payload)


@pytest.mark.parametrize(
    "data",
    [
        wire(extra="nope"),
        payload_with(extra="nope"),
        payload_with(type="deployment"),
        wire(occurred_at="2026-11-13T10:00:00"),
        wire(repo="widgets"),
        wire(repo="acme/ widgets"),
        payload_with(number=0),
        payload_with(action="merged"),
    ],
    ids=[
        "extra-top-level-field",
        "extra-payload-field",
        "unknown-type",
        "naive-datetime",
        "repo-without-owner",
        "repo-with-whitespace",
        "non-positive-number",
        "unknown-action",
    ],
)
def test_invalid_event_is_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Event.model_validate(data)
