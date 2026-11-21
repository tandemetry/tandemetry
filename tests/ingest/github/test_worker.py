import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tandemetry.events.envelope import Event
from tandemetry.events.ports import Record
from tandemetry.ingest.github.normalizer import WebhookNormalizer
from tandemetry.ingest.github.ports import (
    GitHubApiError,
    GitHubNotFoundError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
)
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.worker import (
    NormalizerStalledError,
    NormalizerWorker,
    RetryPolicy,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
RETRY = RetryPolicy(initial_s=1.0, max_s=4.0, rate_limit_max_wait_s=600.0, batch_deadline_s=900.0)

Payload = dict[str, Any]
RawFactory = Callable[[str, Payload], RawWebhook]


class FakeBatchSource:
    def __init__(self, records: Sequence[Record]) -> None:
        self._records = records
        self.commits = 0

    async def next_batch(self) -> Sequence[Record]:
        return self._records

    async def commit(self) -> None:
        self.commits += 1


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.published.append(event)


class ScriptedApi:
    def __init__(self, *failures: GitHubApiError) -> None:
        self._failures = list(failures)
        self.calls = 0

    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        return []

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return []


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def record(value: bytes, offset: int = 0) -> Record:
    return Record("raw.github", 0, offset, value)


def run_once(
    records: Sequence[Record], api: ScriptedApi, sleeps: Sleeps | None = None
) -> tuple[int, FakeBatchSource, FakePublisher]:
    source, publisher = FakeBatchSource(records), FakePublisher()
    worker = NormalizerWorker(
        source,
        WebhookNormalizer(api),
        publisher,
        RETRY,
        sleep=sleeps or Sleeps(),
        clock=lambda: NOW,
    )
    return asyncio.run(worker.run_once()), source, publisher


@pytest.fixture
def opened(make_raw: RawFactory, pull_request_payload: Payload) -> Record:
    return record(make_raw("pull_request", pull_request_payload).model_dump_json().encode())


def test_events_of_every_delivery_are_published_before_one_commit(
    make_raw: RawFactory, opened: Record, review_payload: Payload
) -> None:
    review = record(make_raw("pull_request_review", review_payload).model_dump_json().encode(), 1)
    published, source, publisher = run_once([opened, review], ScriptedApi())
    assert published == len(publisher.published) == 2
    assert source.commits == 1


def test_empty_batch_commits_nothing() -> None:
    assert run_once([], ScriptedApi())[1].commits == 0


def test_invalid_raw_record_is_skipped_without_logging_its_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        published, source, _ = run_once([record(b'{"body": "customer text"}')], ScriptedApi())
    assert (published, source.commits) == (0, 1)
    assert "raw.github[0]@0" in caplog.text
    assert "customer text" not in caplog.text


def test_invalid_delivery_is_skipped(make_raw: RawFactory, ping_payload: Payload) -> None:
    broken = record(make_raw("pull_request", ping_payload).model_dump_json().encode())
    published, source, _ = run_once([broken], ScriptedApi())
    assert (published, source.commits) == (0, 1)


def test_vanished_pull_request_is_skipped(opened: Record) -> None:
    published, source, _ = run_once([opened], ScriptedApi(GitHubNotFoundError("gone")))
    assert (published, source.commits) == (0, 1)


def test_rate_limit_is_waited_out_then_retried(opened: Record) -> None:
    sleeps = Sleeps()
    api = ScriptedApi(GitHubRateLimitedError(NOW + timedelta(seconds=90)))
    published, _, _ = run_once([opened], api, sleeps)
    assert (published, api.calls, sleeps.waits) == (1, 2, [90.0])


def test_transient_failures_back_off_exponentially_up_to_the_cap(opened: Record) -> None:
    sleeps = Sleeps()
    api = ScriptedApi(*(GitHubUnavailableError("HTTP 502") for _ in range(4)))
    published, _, _ = run_once([opened], api, sleeps)
    assert (published, sleeps.waits) == (1, [1.0, 2.0, 4.0, 4.0])


def test_other_api_failure_stops_without_commit(opened: Record) -> None:
    source, publisher = FakeBatchSource([opened]), FakePublisher()
    worker = NormalizerWorker(
        source, WebhookNormalizer(ScriptedApi(GitHubApiError("HTTP 401"))), publisher, RETRY
    )
    with pytest.raises(GitHubApiError, match="401"):
        asyncio.run(worker.run_once())
    assert (source.commits, publisher.published) == (0, [])


@pytest.mark.parametrize(("until_reset", "wait"), [(-5.0, 1.0), (30.0, 30.0), (7200.0, 600.0)])
def test_rate_limit_wait_is_clamped(until_reset: float, wait: float) -> None:
    assert RETRY.rate_limit_wait(until_reset) == wait


def test_backoff_stays_finite_after_many_attempts() -> None:
    assert RETRY.backoff(10_000) == RETRY.max_s


class AdvancingClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_batch_that_outlasts_its_deadline_stops_without_commit(opened: Record) -> None:
    clock = AdvancingClock()
    rate_limits = (GitHubRateLimitedError(NOW + timedelta(days=1)) for _ in range(3))
    source, publisher = FakeBatchSource([opened, opened]), FakePublisher()
    worker = NormalizerWorker(
        source,
        WebhookNormalizer(ScriptedApi(*rate_limits)),
        publisher,
        RETRY,
        sleep=clock.sleep,
        clock=clock,
    )
    with pytest.raises(NormalizerStalledError, match="900s"):
        asyncio.run(worker.run_once())
    assert clock.now == NOW + timedelta(seconds=600)
    assert source.commits == 0
