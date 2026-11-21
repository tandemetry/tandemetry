import asyncio
import hashlib
import hmac
import json
from typing import Any

import pytest
from pydantic import SecretStr

from tandemetry.ingest.github.mapper import InvalidWebhookError
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.receiver import InvalidSignatureError, Receipt, WebhookReceiver
from tandemetry.ingest.github.signature import WebhookSignature

WEBHOOK_KEY = "receiver-test-key"
DELIVERY_ID = "72d3162e-cc78-11e3-81ab-4c9367dc0958"


class FakeRawPublisher:
    def __init__(self) -> None:
        self.published: list[RawWebhook] = []

    async def publish(self, webhook: RawWebhook) -> None:
        self.published.append(webhook)


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_KEY.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def publisher() -> FakeRawPublisher:
    return FakeRawPublisher()


@pytest.fixture
def receiver(publisher: FakeRawPublisher) -> WebhookReceiver:
    return WebhookReceiver(WebhookSignature(SecretStr(WEBHOOK_KEY)), publisher)


def receive(receiver: WebhookReceiver, event: str, body: bytes, signature: str | None) -> Receipt:
    return asyncio.run(receiver.receive(event, DELIVERY_ID, signature, body))


def test_signed_supported_delivery_is_published_unchanged(
    receiver: WebhookReceiver, publisher: FakeRawPublisher, pull_request_payload: dict[str, Any]
) -> None:
    body = json.dumps(pull_request_payload).encode()
    assert receive(receiver, "pull_request", body, sign(body)) is Receipt.ACCEPTED
    assert publisher.published == [
        RawWebhook(
            delivery_id=DELIVERY_ID, event="pull_request", repo_id=1296269, body=body.decode()
        )
    ]


@pytest.mark.parametrize("signature", [None, "sha256=" + "0" * 64])
def test_unsigned_or_forged_delivery_is_rejected_before_parsing(
    receiver: WebhookReceiver, publisher: FakeRawPublisher, signature: str | None
) -> None:
    with pytest.raises(InvalidSignatureError):
        receive(receiver, "pull_request", b"not json", signature)
    assert publisher.published == []


def test_unsupported_event_is_ignored(
    receiver: WebhookReceiver, publisher: FakeRawPublisher, ping_payload: dict[str, Any]
) -> None:
    body = json.dumps(ping_payload).encode()
    assert receive(receiver, "ping", body, sign(body)) is Receipt.IGNORED
    assert publisher.published == []


@pytest.mark.parametrize("body", [b"not json", b'{"action": "opened"}', b"\xff\xfe"])
def test_signed_malformed_delivery_is_invalid(
    receiver: WebhookReceiver, publisher: FakeRawPublisher, body: bytes
) -> None:
    with pytest.raises(InvalidWebhookError):
        receive(receiver, "pull_request", body, sign(body))
    assert publisher.published == []
