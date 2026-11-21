from enum import StrEnum

from pydantic import ValidationError

from tandemetry.events.validation import describe
from tandemetry.ingest.github.mapper import WEBHOOK_MODELS, InvalidWebhookError
from tandemetry.ingest.github.ports import RawWebhookPublisher
from tandemetry.ingest.github.raw import RawWebhook
from tandemetry.ingest.github.signature import WebhookSignature
from tandemetry.ingest.github.webhooks import RepositoryWebhook


class InvalidSignatureError(Exception):
    """A delivery whose signature does not match the webhook secret."""


class Receipt(StrEnum):
    ACCEPTED = "accepted"
    IGNORED = "ignored"


class WebhookReceiver:
    """Accepts signed deliveries of supported events onto the raw stream, unchanged."""

    def __init__(self, signature: WebhookSignature, publisher: RawWebhookPublisher) -> None:
        self._signature = signature
        self._publisher = publisher

    async def receive(
        self, event: str, delivery_id: str, signature: str | None, body: bytes
    ) -> Receipt:
        if not self._signature.matches(body, signature):
            raise InvalidSignatureError
        if event not in WEBHOOK_MODELS:
            return Receipt.IGNORED
        try:
            text = body.decode()
            repository = RepositoryWebhook.model_validate_json(text).repository
            raw = RawWebhook(delivery_id=delivery_id, event=event, repo_id=repository.id, body=text)
        except UnicodeDecodeError:
            raise InvalidWebhookError("body is not UTF-8") from None
        except ValidationError as error:
            raise InvalidWebhookError(describe(error)) from None
        await self._publisher.publish(raw)
        return Receipt.ACCEPTED
