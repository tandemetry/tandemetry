from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from tandemetry.ingest.github.auth import AppTokenProvider
from tandemetry.ingest.github.ports import GitHubApiError
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.transport import GitHubTransport
from tandemetry.settings import GitHubSettings

PAGE_SIZE = 100

FILES = TypeAdapter(list[PullRequestFile])
COMMITS = TypeAdapter(list[PullRequestCommit])


class HttpGitHubApi:
    """Read-only GitHub REST API client authenticated as an App installation."""

    def __init__(self, transport: GitHubTransport, tokens: AppTokenProvider) -> None:
        self._transport = transport
        self._tokens = tokens

    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        return await self._pages(installation_id, f"/repos/{repo}/pulls/{number}/files", FILES)

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        return await self._pages(installation_id, f"/repos/{repo}/pulls/{number}/commits", COMMITS)

    async def _pages[Item: BaseModel](
        self, installation_id: int, path: str, items: TypeAdapter[list[Item]]
    ) -> list[Item]:
        token = await self._tokens.token(installation_id)
        collected: list[Item] = []
        url: str | None = path
        params: dict[str, str | int] | None = {"per_page": PAGE_SIZE}
        while url is not None:
            response = await self._transport.send("GET", url, token, params)
            try:
                collected.extend(items.validate_json(response.content))
            except ValidationError:
                raise GitHubApiError(f"GET {path}: unexpected response") from None
            url = response.links.get("next", {}).get("url")
            params = None
        return collected


@asynccontextmanager
async def github_api(settings: GitHubSettings) -> AsyncIterator[HttpGitHubApi]:
    """A GitHub API client for the configured App, open for the block."""
    async with httpx.AsyncClient(
        base_url=settings.api_url, timeout=settings.request_timeout_s
    ) as http:
        transport = GitHubTransport(http)
        tokens = AppTokenProvider(settings.client_id, settings.private_key, transport)
        yield HttpGitHubApi(transport, tokens)
