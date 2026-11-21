from pydantic import Field, PositiveInt

from tandemetry.events.payloads import DomainModel


class RawWebhook(DomainModel):
    """A verified GitHub webhook delivery as received, kept for normalization and replay."""

    delivery_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    repo_id: PositiveInt
    body: str
