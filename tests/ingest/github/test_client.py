import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from tandemetry.ingest.github.auth import AppTokenProvider
from tandemetry.ingest.github.client import HttpGitHubApi
from tandemetry.ingest.github.ports import (
    GitHubApiError,
    GitHubNotFoundError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
)
from tandemetry.ingest.github.rest import PullRequestFile
from tandemetry.ingest.github.transport import GitHubTransport

API_URL = "https://api.github.test"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
INSTALLATION_TOKEN = "ghs_installation"  # noqa: S105
REPO = "octocat/Hello-World"

Handler = Callable[[httpx.Request], httpx.Response]


def private_key() -> SecretStr:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return SecretStr(pem.decode())


PRIVATE_KEY = private_key()


class GitHubStub:
    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/app/installations/1/access_tokens":
            return httpx.Response(
                201, json={"token": INSTALLATION_TOKEN, "expires_at": "2026-11-21T13:00:00Z"}
            )
        return self._handler(request)


def with_api[T](stub: GitHubStub, call: Callable[[HttpGitHubApi], Awaitable[T]]) -> T:
    async def run() -> T:
        async with httpx.AsyncClient(base_url=API_URL, transport=httpx.MockTransport(stub)) as http:
            transport = GitHubTransport(http, clock=lambda: NOW)
            tokens = AppTokenProvider("Iv1.client", PRIVATE_KEY, transport, clock=lambda: NOW)
            return await call(HttpGitHubApi(transport, tokens))

    return asyncio.run(run())


def call_files(stub: GitHubStub) -> Sequence[PullRequestFile]:
    return with_api(stub, lambda api: api.pull_request_files(1, REPO, 1347))


def file_json(name: str) -> dict[str, object]:
    return {"filename": name, "additions": 1, "deletions": 0, "patch": "@@ secret code @@"}


def test_files_are_collected_across_pages_with_api_headers() -> None:
    def pages(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[file_json("b.py")])
        next_link = f'<{API_URL}/repos/{REPO}/pulls/1347/files?page=2>; rel="next"'
        return httpx.Response(200, json=[file_json("a.py")], headers={"Link": next_link})

    stub = GitHubStub(pages)
    files = call_files(stub)
    assert [file.filename for file in files] == ["a.py", "b.py"]
    token_request, first_page, second_page = stub.requests
    assert first_page.url.params["per_page"] == "100"
    for request in (first_page, second_page):
        assert request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {INSTALLATION_TOKEN}"
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
        assert request.headers["User-Agent"] == "tandemetry"
    assert token_request.method == "POST"


def test_commits_endpoint_is_read() -> None:
    stub = GitHubStub(lambda request: httpx.Response(200, json=[]))
    assert with_api(stub, lambda api: api.pull_request_commits(1, REPO, 1347)) == []
    assert stub.requests[-1].url.path == f"/repos/{REPO}/pulls/1347/commits"


@pytest.mark.parametrize(
    ("response", "retry_at"),
    [
        (
            httpx.Response(
                403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1795349400"}
            ),
            datetime.fromtimestamp(1795349400, UTC),
        ),
        (
            httpx.Response(429, headers={"retry-after": "30"}),
            datetime(2026, 11, 21, 12, 0, 30, tzinfo=UTC),
        ),
        (
            httpx.Response(403, headers={"retry-after": "5"}),
            datetime(2026, 11, 21, 12, 0, 5, tzinfo=UTC),
        ),
    ],
)
def test_rate_limit_reports_when_to_retry(response: httpx.Response, retry_at: datetime) -> None:
    with pytest.raises(GitHubRateLimitedError) as error:
        call_files(GitHubStub(lambda request: response))
    assert error.value.retry_at == retry_at


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (404, GitHubNotFoundError),
        (410, GitHubNotFoundError),
        (502, GitHubUnavailableError),
        (401, GitHubApiError),
        (403, GitHubApiError),
    ],
)
def test_failures_are_typed_without_body_or_token(
    status: int, error_type: type[GitHubApiError]
) -> None:
    response = httpx.Response(status, json={"message": "sensitive detail"})
    with pytest.raises(GitHubApiError) as error:
        call_files(GitHubStub(lambda request: response))
    assert type(error.value) is error_type
    assert "sensitive detail" not in str(error.value)
    assert INSTALLATION_TOKEN not in str(error.value)


def test_connection_failure_is_unavailable() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(GitHubUnavailableError, match="ConnectError"):
        call_files(GitHubStub(broken))


def test_unexpected_response_shape_is_an_api_error() -> None:
    stub = GitHubStub(lambda request: httpx.Response(200, json={"message": "not a list"}))
    with pytest.raises(GitHubApiError, match="unexpected response"):
        call_files(stub)


def test_only_the_token_request_is_not_a_read() -> None:
    stub = GitHubStub(lambda request: httpx.Response(200, json=[file_json("a.py")]))
    call_files(stub)
    writes = [request for request in stub.requests if request.method != "GET"]
    assert [request.url.path for request in writes] == ["/app/installations/1/access_tokens"]
    assert all(str(request.url).startswith(API_URL) for request in stub.requests)
    assert json.loads(writes[0].content or b"{}") == {}
