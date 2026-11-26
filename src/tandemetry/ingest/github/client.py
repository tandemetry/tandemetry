from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping, Sequence
from contextlib import aclosing, asynccontextmanager
from datetime import datetime

import httpx
from pydantic import TypeAdapter, ValidationError

from tandemetry.ingest.github.auth import AppTokenProvider
from tandemetry.ingest.github.ports import GitHubApiError
from tandemetry.ingest.github.rest import CheckRunsPage, PullRequestCommit, PullRequestFile
from tandemetry.ingest.github.transport import GitHubTransport
from tandemetry.ingest.github.webhooks import CheckRunData, PullRequestData, Repository, ReviewData
from tandemetry.settings import GitHubSettings

PAGE_SIZE = 100
PULLS_QUERY = {"state": "all", "sort": "updated", "direction": "desc"}
CHECK_RUNS_QUERY = {"filter": "all"}

FILES = TypeAdapter(list[PullRequestFile])
COMMITS = TypeAdapter(list[PullRequestCommit])
PULLS = TypeAdapter(list[PullRequestData])
REVIEWS = TypeAdapter(list[ReviewData])


def _check_runs(body: bytes) -> Sequence[CheckRunData]:
    return CheckRunsPage.model_validate_json(body).check_runs


class HttpGitHubApi:
    """Read-only GitHub REST API client authenticated as an App installation."""

    def __init__(self, transport: GitHubTransport, tokens: AppTokenProvider) -> None:
        self._transport = transport
        self._tokens = tokens

    async def repository(self, installation_id: int, repo: str) -> Repository:
        token = await self._tokens.token(installation_id)
        path = f"/repos/{repo}"
        response = await self._transport.send("GET", path, token)
        return _parse(path, Repository.model_validate_json, response.content)

    async def pull_requests(
        self, installation_id: int, repo: str, since: datetime | None
    ) -> Sequence[PullRequestData]:
        collected: list[PullRequestData] = []
        pages = self._pages(
            installation_id, f"/repos/{repo}/pulls", PULLS.validate_json, PULLS_QUERY
        )
        async with aclosing(pages):
            async for page in pages:
                fresh = [pull for pull in page if since is None or pull.updated_at >= since]
                collected.extend(fresh)
                if len(fresh) < len(page):
                    break
        return collected

    async def pull_request_reviews(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[ReviewData]:
        path = f"/repos/{repo}/pulls/{number}/reviews"
        return await self._all(installation_id, path, REVIEWS.validate_json)

    async def check_runs(self, installation_id: int, repo: str, sha: str) -> Sequence[CheckRunData]:
        path = f"/repos/{repo}/commits/{sha}/check-runs"
        return await self._all(installation_id, path, _check_runs, CHECK_RUNS_QUERY)

    async def pull_request_files(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestFile]:
        path = f"/repos/{repo}/pulls/{number}/files"
        return await self._all(installation_id, path, FILES.validate_json)

    async def pull_request_commits(
        self, installation_id: int, repo: str, number: int
    ) -> Sequence[PullRequestCommit]:
        path = f"/repos/{repo}/pulls/{number}/commits"
        return await self._all(installation_id, path, COMMITS.validate_json)

    async def _all[Item](
        self,
        installation_id: int,
        path: str,
        parse: Callable[[bytes], Sequence[Item]],
        query: Mapping[str, str] | None = None,
    ) -> list[Item]:
        return [
            item async for page in self._pages(installation_id, path, parse, query) for item in page
        ]

    async def _pages[Item](
        self,
        installation_id: int,
        path: str,
        parse: Callable[[bytes], Sequence[Item]],
        query: Mapping[str, str] | None = None,
    ) -> AsyncGenerator[Sequence[Item]]:
        url: str | None = path
        params: dict[str, str | int] | None = {"per_page": PAGE_SIZE, **(query or {})}
        while url is not None:
            token = await self._tokens.token(installation_id)
            response = await self._transport.send("GET", url, token, params)
            yield _parse(path, parse, response.content)
            url = response.links.get("next", {}).get("url")
            params = None


def _parse[Result](path: str, parse: Callable[[bytes], Result], body: bytes) -> Result:
    try:
        return parse(body)
    except ValidationError:
        raise GitHubApiError(f"GET {path}: unexpected response") from None


@asynccontextmanager
async def github_api(settings: GitHubSettings) -> AsyncIterator[HttpGitHubApi]:
    """A GitHub API client for the configured App, open for the block."""
    async with httpx.AsyncClient(
        base_url=settings.api_url, timeout=settings.request_timeout_s
    ) as http:
        transport = GitHubTransport(http)
        tokens = AppTokenProvider(settings.client_id, settings.private_key, transport)
        yield HttpGitHubApi(transport, tokens)
