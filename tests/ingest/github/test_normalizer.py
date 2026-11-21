import asyncio
from collections.abc import Callable, Sequence
from typing import Any

from tandemetry.events.envelope import Event
from tandemetry.events.payloads import Commit, Merge, PullRequest, Review
from tandemetry.ingest.github.normalizer import WebhookNormalizer
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile

Payload = dict[str, Any]
RawFactory = Callable[[str, Payload], RawWebhook]


class FakeGitHubApi:
    def __init__(
        self, files: Sequence[PullRequestFile], commits: Sequence[PullRequestCommit]
    ) -> None:
        self._files = files
        self._commits = commits
        self.calls: list[tuple[str, int, str, int]] = []

    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        self.calls.append(("files", installation_id, repo, number))
        return self._files

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        self.calls.append(("commits", installation_id, repo, number))
        return self._commits


def normalize(api: FakeGitHubApi, raw: RawWebhook) -> list[Event]:
    return asyncio.run(WebhookNormalizer(api).normalize(raw))


def types(events: list[Event]) -> list[type]:
    return [type(event.payload) for event in events]


def test_opened_pull_request_yields_the_pull_request_and_its_commits(
    make_raw: RawFactory,
    pull_request_payload: Payload,
    files: list[PullRequestFile],
    commits: list[PullRequestCommit],
) -> None:
    api = FakeGitHubApi(files, commits)
    events = normalize(api, make_raw("pull_request", pull_request_payload))
    assert types(events) == [PullRequest, Commit, Commit]
    assert api.calls == [("commits", 1, "octocat/Hello-World", 1347)]


def test_synchronize_refetches_commits_with_stable_ids(
    make_raw: RawFactory,
    pull_request_payload: Payload,
    files: list[PullRequestFile],
    commits: list[PullRequestCommit],
) -> None:
    pull_request_payload["action"] = "synchronize"
    api = FakeGitHubApi(files, commits)
    raw = make_raw("pull_request", pull_request_payload)
    first, second = normalize(api, raw), normalize(api, raw)
    assert types(first) == [Commit, Commit]
    assert [event.event_id for event in first] == [event.event_id for event in second]


def test_merged_pull_request_yields_the_close_and_the_merge(
    make_raw: RawFactory,
    merged_payload: Payload,
    files: list[PullRequestFile],
    commits: list[PullRequestCommit],
) -> None:
    api = FakeGitHubApi(files, commits)
    events = normalize(api, make_raw("pull_request", merged_payload))
    assert types(events) == [PullRequest, Merge]
    assert api.calls == [("files", 1, "octocat/Hello-World", 1347)]


def test_merge_by_a_deleted_author_is_still_recorded(
    make_raw: RawFactory,
    merged_payload: Payload,
    files: list[PullRequestFile],
    commits: list[PullRequestCommit],
) -> None:
    merged_payload["pull_request"]["user"] = None
    events = normalize(FakeGitHubApi(files, commits), make_raw("pull_request", merged_payload))
    assert types(events) == [Merge]


def test_unmerged_close_review_and_check_run_need_no_api_call(
    make_raw: RawFactory,
    pull_request_payload: Payload,
    review_payload: Payload,
    check_run_payload: Payload,
) -> None:
    pull_request_payload["action"] = "closed"
    pull_request_payload["pull_request"]["closed_at"] = "2011-01-28T09:00:00Z"
    api = FakeGitHubApi([], [])
    events = [
        *normalize(api, make_raw("pull_request", pull_request_payload)),
        *normalize(api, make_raw("pull_request_review", review_payload)),
        *normalize(api, make_raw("check_run", check_run_payload)),
    ]
    assert len(events) == 3
    assert isinstance(events[1].payload, Review)
    assert api.calls == []


def test_unsupported_event_yields_nothing(make_raw: RawFactory, ping_payload: Payload) -> None:
    assert normalize(FakeGitHubApi([], []), make_raw("ping", ping_payload)) == []
