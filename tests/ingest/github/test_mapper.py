from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from tandemetry.events.envelope import Event
from tandemetry.events.payloads import (
    CheckConclusion,
    CheckRun,
    Commit,
    FileChange,
    Merge,
    PullRequest,
    PullRequestAction,
    Review,
)
from tandemetry.ingest.github.mapper import (
    InvalidWebhookError,
    check_run_event,
    commit_events,
    merge_event,
    parse_webhook,
    pull_request_action,
    pull_request_event,
    review_event,
)
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.webhooks import CheckRunWebhook, PullRequestWebhook, ReviewWebhook

Payload = dict[str, Any]
RawFactory = Callable[[str, Payload], RawWebhook]


def pull_request(payload: Payload) -> PullRequestWebhook:
    return PullRequestWebhook.model_validate(payload)


def pull_request_fact(payload: Payload) -> Event | None:
    webhook = pull_request(payload)
    action = pull_request_action(webhook.action)
    assert action is not None
    return pull_request_event(webhook.repository, webhook.pull_request, action)


def merge(payload: Payload, files: list[PullRequestFile]) -> Event:
    webhook = pull_request(payload)
    return merge_event(webhook.repository, webhook.pull_request, files)


def review(payload: Payload) -> Event | None:
    webhook = ReviewWebhook.model_validate(payload)
    return review_event(webhook.repository, webhook.pull_request.number, webhook.review)


def check_run(payload: Payload) -> Event:
    webhook = CheckRunWebhook.model_validate(payload)
    return check_run_event(webhook.repository, webhook.check_run)


def test_opened_pull_request_maps_to_a_pull_request_fact(pull_request_payload: Payload) -> None:
    event = pull_request_fact(pull_request_payload)
    assert event is not None
    assert (event.repo_id, event.repo) == (1296269, "octocat/Hello-World")
    assert event.occurred_at == datetime(2011, 1, 26, 19, 1, 12, tzinfo=UTC)
    assert event.payload == PullRequest(
        number=1347,
        action=PullRequestAction.OPENED,
        author="octocat",
        body="Please pull these awesome changes in!",
        head_branch="new-topic",
        labels=("bug",),
    )


@pytest.mark.parametrize(
    ("action", "occurred_at"),
    [
        ("edited", datetime(2011, 1, 27, 6, 15, tzinfo=UTC)),
        ("reopened", datetime(2011, 1, 27, 6, 15, tzinfo=UTC)),
        ("closed", datetime(2011, 1, 28, 9, 0, tzinfo=UTC)),
    ],
)
def test_pull_request_action_picks_its_platform_timestamp(
    pull_request_payload: Payload, action: str, occurred_at: datetime
) -> None:
    pull_request_payload["action"] = action
    pull_request_payload["pull_request"]["closed_at"] = "2011-01-28T09:00:00Z"
    event = pull_request_fact(pull_request_payload)
    assert event is not None
    assert event.occurred_at == occurred_at
    assert isinstance(event.payload, PullRequest)
    assert event.payload.action == action


def test_closed_pull_request_without_closed_at_is_invalid(pull_request_payload: Payload) -> None:
    pull_request_payload["action"] = "closed"
    with pytest.raises(InvalidWebhookError, match="closed_at"):
        pull_request_fact(pull_request_payload)


def test_missing_body_maps_to_empty_text(pull_request_payload: Payload) -> None:
    pull_request_payload["pull_request"]["body"] = None
    event = pull_request_fact(pull_request_payload)
    assert event is not None
    assert isinstance(event.payload, PullRequest)
    assert event.payload.body == ""


def test_deleted_author_has_no_pull_request_fact(pull_request_payload: Payload) -> None:
    pull_request_payload["pull_request"]["user"] = None
    assert pull_request_fact(pull_request_payload) is None


def test_merged_pull_request_maps_to_a_merge_with_its_files(
    merged_payload: Payload, files: list[PullRequestFile]
) -> None:
    event = merge(merged_payload, files)
    assert event.occurred_at == datetime(2011, 1, 28, 10, 0, tzinfo=UTC)
    assert event.payload == Merge(
        pull_request=1347,
        merge_commit_sha="e5bd3914e2e596debea16f433f57875b5b90bcd6",
        files=(
            FileChange(path="file1.txt", additions=103, deletions=21),
            FileChange(path="src/app.py", additions=1, deletions=0),
        ),
    )
    assert "@@" not in event.model_dump_json()


def test_merge_of_an_unmerged_pull_request_is_invalid(pull_request_payload: Payload) -> None:
    with pytest.raises(InvalidWebhookError, match="merged_at"):
        merge(pull_request_payload, [])


def test_commits_map_to_commit_facts_timed_by_committer_date(
    pull_request_payload: Payload, commits: list[PullRequestCommit]
) -> None:
    webhook = pull_request(pull_request_payload)
    events = commit_events(webhook.repository, webhook.pull_request.number, commits)
    assert [event.occurred_at for event in events] == [
        datetime(2011, 4, 14, 16, 30, 49, tzinfo=UTC),
        datetime(2011, 4, 15, 10, 0, tzinfo=UTC),
    ]
    assert [event.payload for event in events] == [
        Commit(
            sha="6dcb09b5b57875f334f61aebed695e2e4193db5e",
            pull_request=1347,
            author_login="octocat",
            author_email="support@github.com",
            message="Fix all the bugs",
        ),
        Commit(
            sha="ce587453ced02b1526dfb4cb910479d431683101",
            pull_request=1347,
            author_login=None,
            author_email="noreply@anthropic.com",
            message="Add tests\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
        ),
    ]


def test_submitted_review_maps_to_a_review_fact(review_payload: Payload) -> None:
    event = review(review_payload)
    assert event is not None
    assert event.occurred_at == datetime(2019, 11, 17, 17, 43, 43, tzinfo=UTC)
    assert event.payload == Review(review_id=80, pull_request=1347, reviewer="hubot")


def test_deleted_reviewer_has_no_fact(review_payload: Payload) -> None:
    review_payload["review"]["user"] = None
    assert review(review_payload) is None


def test_review_without_submitted_at_is_invalid(review_payload: Payload) -> None:
    review_payload["review"]["submitted_at"] = None
    with pytest.raises(InvalidWebhookError, match="submitted_at"):
        review(review_payload)


def test_completed_check_run_maps_to_a_check_run_fact(check_run_payload: Payload) -> None:
    event = check_run(check_run_payload)
    assert event.occurred_at == datetime(2018, 5, 4, 1, 15, 40, tzinfo=UTC)
    assert event.payload == CheckRun(
        check_run_id=4,
        name="test",
        head_sha="ce587453ced02b1526dfb4cb910479d431683101",
        conclusion=CheckConclusion.FAILURE,
    )


def test_completed_check_run_without_conclusion_is_invalid(check_run_payload: Payload) -> None:
    check_run_payload["check_run"]["conclusion"] = None
    with pytest.raises(InvalidWebhookError, match="conclusion"):
        check_run(check_run_payload)


def test_unsupported_event_parses_to_nothing(make_raw: RawFactory, ping_payload: Payload) -> None:
    assert parse_webhook(make_raw("ping", ping_payload)) is None


def test_wrong_shape_is_invalid_without_echoing_values(
    make_raw: RawFactory, ping_payload: Payload
) -> None:
    with pytest.raises(InvalidWebhookError) as error:
        parse_webhook(make_raw("pull_request", ping_payload))
    assert "pull_request: missing" in str(error.value)
    assert "Keep it logically awesome" not in str(error.value)


def test_invalid_sha_is_invalid_without_echoing_values(check_run_payload: Payload) -> None:
    check_run_payload["check_run"]["head_sha"] = "not-a-sha"
    with pytest.raises(InvalidWebhookError) as error:
        check_run(check_run_payload)
    assert "not-a-sha" not in str(error.value)


def test_redelivery_maps_to_the_same_event_id(
    make_raw: RawFactory, pull_request_payload: Payload
) -> None:
    first, second = (
        parse_webhook(make_raw("pull_request", pull_request_payload)) for _ in range(2)
    )
    assert isinstance(first, PullRequestWebhook)
    assert isinstance(second, PullRequestWebhook)
    first_event, second_event = (
        pull_request_event(webhook.repository, webhook.pull_request, PullRequestAction.OPENED)
        for webhook in (first, second)
    )
    assert first_event is not None
    assert second_event is not None
    assert first_event.event_id == second_event.event_id


def test_only_tracked_webhook_actions_map_to_pull_request_actions() -> None:
    assert [pull_request_action(action) for action in ("opened", "labeled", "synchronize")] == [
        PullRequestAction.OPENED,
        None,
        None,
    ]
