import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.rest import PullRequestCommit, PullRequestFile

FIXTURES = Path(__file__).parent / "fixtures"

Payload = dict[str, Any]


def read_fixture(name: str) -> Payload:
    payload: Payload = json.loads((FIXTURES / name).read_text())
    return payload


@pytest.fixture
def pull_request_payload() -> Payload:
    return read_fixture("pull_request.json")


@pytest.fixture
def merged_payload(pull_request_payload: Payload) -> Payload:
    payload = copy.deepcopy(pull_request_payload)
    payload["action"] = "closed"
    payload["pull_request"].update(
        closed_at="2011-01-28T10:00:00Z",
        merged_at="2011-01-28T10:00:00Z",
        merged=True,
        merge_commit_sha="e5bd3914e2e596debea16f433f57875b5b90bcd6",
    )
    return payload


@pytest.fixture
def review_payload() -> Payload:
    return read_fixture("pull_request_review.json")


@pytest.fixture
def check_run_payload() -> Payload:
    return read_fixture("check_run.json")


@pytest.fixture
def ping_payload() -> Payload:
    return read_fixture("ping.json")


@pytest.fixture
def commits_body() -> bytes:
    return (FIXTURES / "pulls_commits.json").read_bytes()


@pytest.fixture
def files_body() -> bytes:
    return (FIXTURES / "pulls_files.json").read_bytes()


@pytest.fixture
def commits(commits_body: bytes) -> list[PullRequestCommit]:
    return TypeAdapter(list[PullRequestCommit]).validate_json(commits_body)


@pytest.fixture
def files(files_body: bytes) -> list[PullRequestFile]:
    return TypeAdapter(list[PullRequestFile]).validate_json(files_body)


@pytest.fixture
def make_raw() -> Callable[[str, Payload], RawWebhook]:
    def make(event: str, payload: Payload) -> RawWebhook:
        return RawWebhook(
            delivery_id="72d3162e-cc78-11e3-81ab-4c9367dc0958",
            event=event,
            repo_id=1296269,
            body=json.dumps(payload),
        )

    return make
