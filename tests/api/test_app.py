import hashlib
import hmac
import json
from pathlib import Path

import httpx
import pytest
from aiokafka.errors import KafkaConnectionError
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tandemetry.api.app import create_app
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.receiver import WebhookReceiver
from tandemetry.ingest.github.signature import WebhookSignature

WEBHOOK_KEY = "app-test-key"
MAX_BODY_BYTES = 4096
FIXTURES = Path(__file__).parents[1] / "ingest" / "github" / "fixtures"


class FakeRawPublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.published: list[RawWebhook] = []

    async def publish(self, webhook: RawWebhook) -> None:
        if self._error is not None:
            raise self._error
        self.published.append(webhook)


def client_for(publisher: FakeRawPublisher) -> TestClient:
    receiver = WebhookReceiver(WebhookSignature(SecretStr(WEBHOOK_KEY)), publisher)
    return TestClient(create_app(receiver, MAX_BODY_BYTES))


def headers(event: str, body: bytes, signed: bool = True) -> dict[str, str]:
    result = {"X-GitHub-Event": event, "X-GitHub-Delivery": "delivery-1"}
    if signed:
        digest = hmac.new(WEBHOOK_KEY.encode(), body, hashlib.sha256).hexdigest()
        result["X-Hub-Signature-256"] = f"sha256={digest}"
    return result


def deliver(client: TestClient, event: str, body: bytes) -> httpx.Response:
    response: httpx.Response = client.post(
        "/webhooks/github", content=body, headers=headers(event, body)
    )
    return response


@pytest.fixture
def pull_request_body() -> bytes:
    return (FIXTURES / "pull_request.json").read_bytes()


def test_health_probe_answers() -> None:
    response = client_for(FakeRawPublisher()).get("/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_signed_delivery_is_accepted_and_published(pull_request_body: bytes) -> None:
    publisher = FakeRawPublisher()
    response = client_for(publisher).post(
        "/webhooks/github",
        content=pull_request_body,
        headers=headers("pull_request", pull_request_body),
    )
    assert response.status_code == 202
    [published] = publisher.published
    assert (published.delivery_id, published.event, published.repo_id) == (
        "delivery-1",
        "pull_request",
        1296269,
    )


def test_unsigned_delivery_is_unauthorized(pull_request_body: bytes) -> None:
    publisher = FakeRawPublisher()
    response = client_for(publisher).post(
        "/webhooks/github",
        content=pull_request_body,
        headers=headers("pull_request", pull_request_body, signed=False),
    )
    assert response.status_code == 401
    assert publisher.published == []


def test_ping_is_acknowledged_without_publishing() -> None:
    body = (FIXTURES / "ping.json").read_bytes()
    publisher = FakeRawPublisher()
    response = deliver(client_for(publisher), "ping", body)
    assert response.status_code == 204
    assert publisher.published == []


def test_signed_malformed_delivery_is_rejected_without_echo() -> None:
    body = json.dumps({"action": "opened", "secret_field": "customer text"}).encode()
    response = deliver(client_for(FakeRawPublisher()), "pull_request", body)
    assert response.status_code == 400
    assert response.content == b""


def test_kafka_failure_is_reported_as_unavailable(pull_request_body: bytes) -> None:
    publisher = FakeRawPublisher(KafkaConnectionError())
    response = client_for(publisher).post(
        "/webhooks/github",
        content=pull_request_body,
        headers=headers("pull_request", pull_request_body),
    )
    assert response.status_code == 503


def test_oversized_delivery_is_rejected_before_publishing() -> None:
    publisher = FakeRawPublisher()
    body = b"x" * (MAX_BODY_BYTES + 1)
    response = deliver(client_for(publisher), "pull_request", body)
    assert response.status_code == 413
    assert publisher.published == []


def test_oversized_stream_without_length_is_rejected() -> None:
    publisher = FakeRawPublisher()
    chunks = iter([b"x" * MAX_BODY_BYTES, b"x"])
    response = client_for(publisher).post(
        "/webhooks/github", content=chunks, headers={"X-GitHub-Event": "pull_request"}
    )
    assert response.status_code == 413
    assert publisher.published == []
