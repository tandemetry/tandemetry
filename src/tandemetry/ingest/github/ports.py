from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.webhooks import CheckRunData, PullRequestData, Repository, ReviewData


class GitHubApiError(Exception):
    """A GitHub API request that failed and should not be retried as is."""


class GitHubUnavailableError(GitHubApiError):
    """A transient failure: server error, timeout or broken connection."""


class GitHubRateLimitedError(GitHubApiError):
    """The rate limit is exhausted until `retry_at`."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__(f"rate limited until {retry_at.isoformat()}")
        self.retry_at = retry_at


class GitHubNotFoundError(GitHubApiError):
    """The resource or installation no longer exists or is no longer accessible."""


class GitHubApi(Protocol):
    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        """Every file changed by a pull request."""

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        """Every commit of a pull request."""


class GitHubHistoryApi(GitHubApi, Protocol):
    async def repository(self, installation_id: int, repo: str) -> Repository:
        """The repository named `owner/name`."""

    async def pull_requests(
        self, installation_id: int, repo: str, since: datetime | None
    ) -> Sequence[PullRequestData]:
        """Pull requests in any state updated at or after `since`, most recently updated first."""

    async def pull_request_reviews(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[ReviewData]:
        """Every review of a pull request."""

    async def check_runs(self, installation_id: int, repo: str, sha: str) -> Sequence[CheckRunData]:
        """Every check run of a commit, including reruns."""


class RawWebhookPublisher(Protocol):
    async def publish(self, webhook: RawWebhook) -> None:
        """Hand a delivery to the raw stream; publishing it again is allowed."""
