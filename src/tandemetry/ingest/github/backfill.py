import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial

from tandemetry.events.envelope import Event
from tandemetry.events.payloads import PullRequestAction
from tandemetry.events.ports import EventPublisher
from tandemetry.ingest.github.mapper import (
    InvalidWebhookError,
    check_run_event,
    commit_events,
    merge_event,
    pull_request_event,
    review_event,
)
from tandemetry.ingest.github.ports import GitHubHistoryApi, GitHubNotFoundError
from tandemetry.ingest.github.retry import GitHubRetry
from tandemetry.ingest.github.webhooks import PullRequestData, Repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillTarget:
    """The repository of an installation whose pull requests updated since `since` are read."""

    installation_id: int
    repo: str
    since: datetime | None


@dataclass(frozen=True)
class BackfilledPullRequest:
    """A pull request whose history is fully published, or skipped when it could not be read."""

    number: int
    updated_at: datetime
    published: int
    skipped: bool


class Backfill:
    """Publishes the history of pull requests as the events their webhooks would have produced."""

    def __init__(
        self, api: GitHubHistoryApi, publisher: EventPublisher, retry: GitHubRetry
    ) -> None:
        self._api = api
        self._publisher = publisher
        self._retry = retry

    async def run(self, target: BackfillTarget) -> AsyncIterator[BackfilledPullRequest]:
        """Each pull request once its events are published, least recently updated first."""
        deadline = self._retry.deadline()
        repository = await self._retry.call(
            partial(self._api.repository, target.installation_id, target.repo), deadline
        )
        pulls = await self._retry.call(
            partial(self._api.pull_requests, target.installation_id, target.repo, target.since),
            deadline,
        )
        for pull in sorted(pulls, key=lambda pull: pull.updated_at):
            events = await self._events(target.installation_id, repository, pull)
            for event in events or ():
                await self._publisher.publish(event)
            yield BackfilledPullRequest(
                pull.number, pull.updated_at, len(events or ()), skipped=events is None
            )

    async def _events(
        self, installation_id: int, repository: Repository, pull: PullRequestData
    ) -> list[Event] | None:
        try:
            return await _PullRequestHistory(
                self._api, self._retry, installation_id, repository, pull
            ).events()
        except (InvalidWebhookError, GitHubNotFoundError) as error:
            logger.warning("skipped pull request #%d: %s", pull.number, error)
            return None


class _PullRequestHistory:
    def __init__(
        self,
        api: GitHubHistoryApi,
        retry: GitHubRetry,
        installation_id: int,
        repository: Repository,
        pull: PullRequestData,
    ) -> None:
        self._api = api
        self._retry = retry
        self._deadline = retry.deadline()
        self._installation_id = installation_id
        self._repository = repository
        self._pull = pull

    async def events(self) -> list[Event]:
        return [
            *self._pull_request_facts(),
            *await self._commits(),
            *await self._merge(),
            *await self._reviews(),
            *await self._check_runs(),
        ]

    def _pull_request_facts(self) -> list[Event]:
        actions = [PullRequestAction.OPENED]
        if self._pull.closed_at is not None:
            actions.append(PullRequestAction.CLOSED)
        facts = (pull_request_event(self._repository, self._pull, action) for action in actions)
        return [fact for fact in facts if fact is not None]

    async def _commits(self) -> list[Event]:
        commits = await self._fetch(self._api.pull_request_commits)
        return commit_events(self._repository, self._pull.number, commits)

    async def _merge(self) -> list[Event]:
        if self._pull.merged_at is None:
            return []
        files = await self._fetch(self._api.pull_request_files)
        return [merge_event(self._repository, self._pull, files)]

    async def _reviews(self) -> list[Event]:
        reviews = await self._fetch(self._api.pull_request_reviews)
        submitted = (
            review_event(self._repository, self._pull.number, review)
            for review in reviews
            if review.submitted_at is not None
        )
        return [event for event in submitted if event is not None]

    async def _check_runs(self) -> list[Event]:
        runs = await self._retry.call(
            partial(
                self._api.check_runs,
                self._installation_id,
                self._repository.full_name,
                self._pull.head.sha,
            ),
            self._deadline,
        )
        return [
            check_run_event(self._repository, run)
            for run in runs
            if run.conclusion is not None and run.completed_at is not None
        ]

    async def _fetch[Result](self, read: Callable[[int, str, int], Awaitable[Result]]) -> Result:
        request = partial(
            read, self._installation_id, self._repository.full_name, self._pull.number
        )
        return await self._retry.call(request, self._deadline)
