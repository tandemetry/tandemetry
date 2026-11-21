from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

import httpx

from tandemetry.ingest.github.ports import (
    GitHubApiError,
    GitHubNotFoundError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
)

API_VERSION = "2022-11-28"
USER_AGENT = "tandemetry"
DEFAULT_RATE_LIMIT_WAIT = timedelta(seconds=60)
RATE_LIMIT_STATUSES = frozenset((403, 429))
NOT_FOUND_STATUSES = frozenset((404, 410))

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class GitHubTransport:
    """Sends authenticated GitHub API requests and turns failures into typed errors."""

    def __init__(self, http: httpx.AsyncClient, clock: Clock = utc_now) -> None:
        self._http = http
        self._clock = clock

    async def send(
        self,
        method: str,
        url: str,
        token: str,
        params: Mapping[str, str | int] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method,
                url,
                params=params,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": USER_AGENT,
                    "X-GitHub-Api-Version": API_VERSION,
                },
            )
        except httpx.TransportError as error:
            raise GitHubUnavailableError(f"{method} {url}: {type(error).__name__}") from None
        self._raise_for_status(method, response)
        return response

    def _raise_for_status(self, method: str, response: httpx.Response) -> None:
        if response.is_success:
            return
        status, path = response.status_code, response.request.url.path
        if status in RATE_LIMIT_STATUSES and (retry_at := self._retry_at(response)) is not None:
            raise GitHubRateLimitedError(retry_at)
        if status in NOT_FOUND_STATUSES:
            raise GitHubNotFoundError(f"{method} {path}: HTTP {status}")
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise GitHubUnavailableError(f"{method} {path}: HTTP {status}")
        raise GitHubApiError(f"{method} {path}: HTTP {status}")

    def _retry_at(self, response: httpx.Response) -> datetime | None:
        headers = response.headers
        if (retry_after := headers.get("retry-after", "")).isdigit():
            return self._clock() + timedelta(seconds=int(retry_after))
        if headers.get("x-ratelimit-remaining") == "0":
            reset = headers.get("x-ratelimit-reset", "")
            if reset.isdigit():
                return datetime.fromtimestamp(int(reset), UTC)
            return self._clock() + DEFAULT_RATE_LIMIT_WAIT
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            return self._clock() + DEFAULT_RATE_LIMIT_WAIT
        return None
