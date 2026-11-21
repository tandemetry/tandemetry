from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile


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


class RawWebhookPublisher(Protocol):
    async def publish(self, webhook: RawWebhook) -> None:
        """Hand a delivery to the raw stream; publishing it again is allowed."""
