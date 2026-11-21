import asyncio

from tandemetry.ingest.github.kafka import KafkaRawWebhookPublisher
from tandemetry.ingest.github.raw import RawWebhook


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes]] = []

    async def send_and_wait(self, topic: str, value: bytes, key: bytes) -> object:
        self.sent.append((topic, value, key))
        return None


def test_raw_webhook_is_sent_keyed_by_repository() -> None:
    webhook = RawWebhook(delivery_id="d-1", event="pull_request", repo_id=1296269, body="{}")
    sender = FakeSender()
    asyncio.run(KafkaRawWebhookPublisher(sender, "raw.github").publish(webhook))
    [(topic, value, key)] = sender.sent
    assert (topic, key) == ("raw.github", b"1296269")
    assert RawWebhook.model_validate_json(value) == webhook
