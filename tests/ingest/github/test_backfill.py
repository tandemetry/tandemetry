import asyncio
import copy
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer
from pydantic import SecretStr

from tandemetry.cli import BackfillCommand, Cli, PackageVersionProvider
from tandemetry.events.envelope import Event
from tandemetry.events.payloads import PullRequest
from tandemetry.ingest.github.backfill import Backfill, BackfilledPullRequest, BackfillTarget
from tandemetry.ingest.github.normalizer import WebhookNormalizer
from tandemetry.ingest.github.ports import GitHubNotFoundError, GitHubRateLimitedError
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.retry import GitHubRetry, RetryPolicy
from tandemetry.ingest.github.webhooks import (
    CheckRunData,
    PullRequestData,
    Repository,
    ReviewData,
)
from tandemetry.settings import GitHubSettings, KafkaSettings, Settings

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
RETRY = RetryPolicy(initial_s=1.0, max_s=4.0, rate_limit_max_wait_s=600.0, batch_deadline_s=900.0)
REPOSITORY = Repository(id=1296269, full_name="octocat/Hello-World")
TARGET = BackfillTarget(installation_id=1, repo="octocat/Hello-World", since=None)

Payload = dict[str, Any]
RawFactory = Callable[[str, Payload], RawWebhook]


class FakeHistoryApi:
    def __init__(
        self,
        pulls: Sequence[PullRequestData],
        commits: Sequence[PullRequestCommit] = (),
        files: Sequence[PullRequestFile] = (),
        reviews: Sequence[ReviewData] = (),
        runs: Sequence[CheckRunData] = (),
    ) -> None:
        self._pulls = pulls
        self._commits = commits
        self._files = files
        self._reviews = reviews
        self._runs = runs
        self.missing: set[int] = set()
        self.rate_limits = 0
        self.since: list[datetime | None] = []
        self.check_run_shas: list[str] = []
        self.file_reads: list[int] = []

    async def repository(self, installation_id: int, repo: str) -> Repository:
        return REPOSITORY

    async def pull_requests(
        self, installation_id: int, repo: str, since: datetime | None
    ) -> Sequence[PullRequestData]:
        self.since.append(since)
        return self._pulls

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        if number in self.missing:
            raise GitHubNotFoundError(f"pull request {number}")
        if self.rate_limits:
            self.rate_limits -= 1
            raise GitHubRateLimitedError(NOW + timedelta(seconds=30))
        return self._commits

    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        self.file_reads.append(number)
        return self._files

    async def pull_request_reviews(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[ReviewData]:
        return self._reviews

    async def check_runs(self, installation_id: int, repo: str, sha: str) -> Sequence[CheckRunData]:
        self.check_run_shas.append(sha)
        return self._runs


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.published.append(event)


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def run_backfill(
    api: FakeHistoryApi, target: BackfillTarget = TARGET, sleeps: Sleeps | None = None
) -> tuple[list[BackfilledPullRequest], list[Event]]:
    publisher = FakePublisher()
    backfill = Backfill(api, publisher, GitHubRetry(RETRY, sleeps or Sleeps(), lambda: NOW))

    async def collect() -> list[BackfilledPullRequest]:
        return [done async for done in backfill.run(target)]

    return asyncio.run(collect()), publisher.published


def pull(
    payload: Payload, number: int = 1347, updated_at: str = "2026-11-01T00:00:00Z"
) -> PullRequestData:
    data = copy.deepcopy(payload["pull_request"])
    data.update(number=number, updated_at=updated_at)
    return PullRequestData.model_validate(data)


def review(payload: Payload, **changes: object) -> ReviewData:
    return ReviewData.model_validate({**payload["review"], **changes})


def check_run(payload: Payload, **changes: object) -> CheckRunData:
    return CheckRunData.model_validate({**payload["check_run"], **changes})


def test_merged_pull_request_has_the_event_ids_of_its_webhooks(
    pull_request_payload: Payload,
    merged_payload: Payload,
    review_payload: Payload,
    check_run_payload: Payload,
    commits: list[PullRequestCommit],
    files: list[PullRequestFile],
    make_raw: RawFactory,
) -> None:
    merged = PullRequestData.model_validate(merged_payload["pull_request"])
    api = FakeHistoryApi(
        [merged],
        commits,
        files,
        [review(review_payload)],
        [check_run(check_run_payload)],
    )
    _, backfilled = run_backfill(api)

    normalizer = WebhookNormalizer(api)
    webhooks = [
        make_raw("pull_request", pull_request_payload),
        make_raw("pull_request", merged_payload),
        make_raw("pull_request_review", review_payload),
        make_raw("check_run", check_run_payload),
    ]

    async def normalize() -> list[Event]:
        return [event for raw in webhooks for event in await normalizer.normalize(raw)]

    from_webhooks = asyncio.run(normalize())
    assert sorted(event.event_id for event in backfilled) == sorted(
        event.event_id for event in from_webhooks
    )
    assert {event.payload.type for event in backfilled} == {
        "pull_request",
        "commit",
        "merge",
        "review",
        "check_run",
    }
    assert api.check_run_shas == [merged.head.sha]


def test_open_pull_request_is_opened_with_its_commits_and_no_merge(
    pull_request_payload: Payload, commits: list[PullRequestCommit]
) -> None:
    api = FakeHistoryApi([pull(pull_request_payload)], commits)
    _, published = run_backfill(api)
    assert [event.payload.type for event in published] == ["pull_request"] + ["commit"] * len(
        commits
    )
    assert api.file_reads == []


def test_pending_reviews_ghost_reviewers_and_unfinished_check_runs_are_skipped(
    pull_request_payload: Payload, review_payload: Payload, check_run_payload: Payload
) -> None:
    api = FakeHistoryApi(
        [pull(pull_request_payload)],
        reviews=[review(review_payload, submitted_at=None), review(review_payload, user=None)],
        runs=[check_run(check_run_payload, conclusion=None, completed_at=None)],
    )
    _, published = run_backfill(api)
    assert [event.payload.type for event in published] == ["pull_request"]


def test_pull_requests_are_published_least_recently_updated_first(
    pull_request_payload: Payload,
) -> None:
    api = FakeHistoryApi(
        [
            pull(pull_request_payload, 3, "2026-11-20T00:00:00Z"),
            pull(pull_request_payload, 1, "2026-11-01T00:00:00Z"),
            pull(pull_request_payload, 2, "2026-11-10T00:00:00Z"),
        ]
    )
    since = datetime(2026, 10, 1, tzinfo=UTC)
    done, _ = run_backfill(api, BackfillTarget(1, "octocat/Hello-World", since))
    assert [(item.number, item.updated_at.day, item.published) for item in done] == [
        (1, 1, 1),
        (2, 10, 1),
        (3, 20, 1),
    ]
    assert api.since == [since]


def test_a_pull_request_that_is_gone_is_skipped_and_the_rest_continue(
    pull_request_payload: Payload, caplog: pytest.LogCaptureFixture
) -> None:
    api = FakeHistoryApi(
        [
            pull(pull_request_payload, 1, "2026-11-01T00:00:00Z"),
            pull(pull_request_payload, 2, "2026-11-02T00:00:00Z"),
        ]
    )
    api.missing.add(1)
    done, published = run_backfill(api)
    assert [(item.number, item.published, item.skipped) for item in done] == [
        (1, 0, True),
        (2, 1, False),
    ]
    assert [
        event.payload.number for event in published if isinstance(event.payload, PullRequest)
    ] == [2]
    assert "skipped pull request #1" in caplog.text


def test_rate_limit_is_waited_out_and_the_read_retried(
    pull_request_payload: Payload, commits: list[PullRequestCommit]
) -> None:
    api = FakeHistoryApi([pull(pull_request_payload)], commits)
    api.rate_limits = 1
    sleeps = Sleeps()
    done, _ = run_backfill(api, sleeps=sleeps)
    assert sleeps.waits == [30.0]
    assert done[0].published == 1 + len(commits)


RECEIVE_TIMEOUT_SECONDS = 30
APP = GitHubSettings(client_id="Iv1.client", private_key=SecretStr("pem"))


async def receive(settings: KafkaSettings, count: int) -> list[Event]:
    consumer = AIOKafkaConsumer(
        settings.events_topic,
        bootstrap_servers=settings.bootstrap_servers,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        received: list[Event] = []
        async with asyncio.timeout(RECEIVE_TIMEOUT_SECONDS):
            async for message in consumer:
                received.append(Event.model_validate_json(message.value))
                if len(received) == count:
                    return received
        return received
    finally:
        await consumer.stop()


@pytest.mark.integration
def test_backfill_publishes_to_kafka_and_a_rerun_repeats_the_same_ids(
    kafka_settings: KafkaSettings,
    merged_payload: Payload,
    commits: list[PullRequestCommit],
    files: list[PullRequestFile],
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = FakeHistoryApi(
        [PullRequestData.model_validate(merged_payload["pull_request"])], commits, files
    )

    @asynccontextmanager
    async def open_api(settings: GitHubSettings) -> AsyncIterator[FakeHistoryApi]:
        yield api

    cli = Cli(
        PackageVersionProvider(),
        Settings(),
        {"backfill": BackfillCommand(kafka_settings, APP, open_api=open_api)},
    )
    argv = ["backfill", "--installation", "1", "--repo", "octocat/Hello-World"]
    assert cli.run(argv) == 0
    assert cli.run(argv) == 0

    per_run = 2 + len(commits) + 1
    received = asyncio.run(receive(kafka_settings, 2 * per_run))
    assert len(received) == 2 * per_run
    assert len({event.event_id for event in received}) == per_run
    assert {event.repo_id for event in received} == {REPOSITORY.id}
    output = capsys.readouterr().out
    assert (
        f"backfilled #1347 ({per_run} events); resume with --since 2011-01-27T06:15:00+00:00"
        in output
    )
