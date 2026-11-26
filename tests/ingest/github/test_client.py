import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from tandemetry.ingest.github.auth import AppTokenProvider
from tandemetry.ingest.github.client import HttpGitHubApi
from tandemetry.ingest.github.ports import (
    GitHubApiError,
    GitHubHistoryApi,
    GitHubNotFoundError,
    GitHubRateLimitedError,
    GitHubUnavailableError,
)
from tandemetry.ingest.github.rest import PullRequestFile
from tandemetry.ingest.github.transport import GitHubTransport
from tandemetry.ingest.github.webhooks import Repository

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
    def __init__(self, handler: Handler, token_lifetime: timedelta = timedelta(hours=1)) -> None:
        self._handler = handler
        self._token_expires_at = (NOW + token_lifetime).isoformat()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/app/installations/1/access_tokens":
            return httpx.Response(
                201, json={"token": INSTALLATION_TOKEN, "expires_at": self._token_expires_at}
            )
        return self._handler(request)

    def reads(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.method == "GET"]


def with_api[T](stub: GitHubStub, call: Callable[[GitHubHistoryApi], Awaitable[T]]) -> T:
    async def run() -> T:
        async with httpx.AsyncClient(base_url=API_URL, transport=httpx.MockTransport(stub)) as http:
            transport = GitHubTransport(http, clock=lambda: NOW)
            tokens = AppTokenProvider("Iv1.client", PRIVATE_KEY, transport, clock=lambda: NOW)
            api: GitHubHistoryApi = HttpGitHubApi(transport, tokens)
            return await call(api)

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


def pull_json(number: int, updated_at: str) -> dict[str, Any]:
    return {
        "number": number,
        "user": {"login": "octocat"},
        "body": None,
        "head": {"ref": "topic", "sha": "6dcb09b5b57875f334f61aebed695e2e4193db5e"},
        "labels": [],
        "created_at": "2026-11-01T00:00:00Z",
        "updated_at": updated_at,
        "closed_at": None,
        "merged_at": None,
        "merge_commit_sha": None,
    }


def paged(pages: Sequence[object]) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        index = int(request.url.params.get("page", "1")) - 1
        headers = {}
        if index + 1 < len(pages):
            headers["Link"] = f'<{API_URL}{request.url.path}?page={index + 2}>; rel="next"'
        return httpx.Response(200, json=pages[index], headers=headers)

    return handle


PULL_PAGES = [
    [pull_json(3, "2026-11-20T00:00:00Z"), pull_json(2, "2026-11-10T00:00:00Z")],
    [pull_json(1, "2026-11-05T00:00:00Z"), pull_json(9, "2026-10-01T00:00:00Z")],
    [pull_json(8, "2026-09-01T00:00:00Z")],
]


def test_pull_requests_of_any_state_are_read_most_recently_updated_first() -> None:
    stub = GitHubStub(paged(PULL_PAGES))
    pulls = with_api(stub, lambda api: api.pull_requests(1, REPO, None))
    assert [pull.number for pull in pulls] == [3, 2, 1, 9, 8]
    assert pulls[0].head.sha == "6dcb09b5b57875f334f61aebed695e2e4193db5e"
    first_page = stub.reads()[0]
    assert first_page.url.path == f"/repos/{REPO}/pulls"
    assert dict(first_page.url.params) == {
        "per_page": "100",
        "state": "all",
        "sort": "updated",
        "direction": "desc",
    }


def test_pull_request_paging_stops_at_the_first_pull_updated_before_since() -> None:
    stub = GitHubStub(paged(PULL_PAGES))
    since = datetime(2026, 11, 5, tzinfo=UTC)
    pulls = with_api(stub, lambda api: api.pull_requests(1, REPO, since))
    assert [pull.number for pull in pulls] == [3, 2, 1]
    assert len(stub.reads()) == 2


def test_every_page_fetches_the_token_so_a_long_listing_survives_its_expiry() -> None:
    stub = GitHubStub(paged(PULL_PAGES), token_lifetime=timedelta(minutes=1))
    with_api(stub, lambda api: api.pull_requests(1, REPO, None))
    methods = [request.method for request in stub.requests]
    assert methods == ["POST", "GET"] * 3


def test_reviews_of_a_pull_request_are_read() -> None:
    review = {"id": 80, "user": {"login": "hubot"}, "submitted_at": "2019-11-17T17:43:43Z"}
    stub = GitHubStub(paged([[review]]))
    reviews = with_api(stub, lambda api: api.pull_request_reviews(1, REPO, 1347))
    assert [review.id for review in reviews] == [80]
    assert stub.reads()[0].url.path == f"/repos/{REPO}/pulls/1347/reviews"


def check_run_json(run_id: int) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": "test",
        "head_sha": "ce587453ced02b1526dfb4cb910479d431683101",
        "conclusion": "failure",
        "completed_at": "2018-05-04T01:15:40Z",
    }


def test_every_check_run_of_a_commit_is_read_from_the_envelope() -> None:
    pages = [
        {"total_count": 3, "check_runs": [check_run_json(4), check_run_json(5)]},
        {"total_count": 3, "check_runs": [check_run_json(6)]},
    ]
    stub = GitHubStub(paged(pages))
    sha = "ce587453ced02b1526dfb4cb910479d431683101"
    runs = with_api(stub, lambda api: api.check_runs(1, REPO, sha))
    assert [run.id for run in runs] == [4, 5, 6]
    first_page = stub.reads()[0]
    assert first_page.url.path == f"/repos/{REPO}/commits/{sha}/check-runs"
    assert first_page.url.params["filter"] == "all"


def test_repository_is_read() -> None:
    stub = GitHubStub(lambda request: httpx.Response(200, json={"id": 7, "full_name": REPO}))
    repository = with_api(stub, lambda api: api.repository(1, REPO))
    assert repository == Repository(id=7, full_name=REPO)
    assert stub.reads()[0].url.path == f"/repos/{REPO}"


HISTORY_CALLS: list[Callable[[GitHubHistoryApi], Awaitable[object]]] = [
    lambda api: api.repository(1, REPO),
    lambda api: api.pull_requests(1, REPO, None),
    lambda api: api.pull_request_reviews(1, REPO, 1347),
    lambda api: api.check_runs(1, REPO, "ce58745"),
]


@pytest.mark.parametrize("call", HISTORY_CALLS)
def test_history_of_a_missing_repository_is_not_found(
    call: Callable[[GitHubHistoryApi], Awaitable[object]],
) -> None:
    with pytest.raises(GitHubNotFoundError):
        with_api(GitHubStub(lambda request: httpx.Response(404)), call)


@pytest.mark.parametrize("call", HISTORY_CALLS)
def test_unexpected_history_shape_is_an_api_error(
    call: Callable[[GitHubHistoryApi], Awaitable[object]],
) -> None:
    stub = GitHubStub(lambda request: httpx.Response(200, json={"check_runs": "nope"}))
    with pytest.raises(GitHubApiError, match="unexpected response"):
        with_api(stub, call)
