import hashlib
import hmac

from pydantic import SecretStr

SIGNATURE_PREFIX = "sha256="


class WebhookSignature:
    """Verifies the `X-Hub-Signature-256` HMAC that GitHub computes over the raw body."""

    def __init__(self, secret: SecretStr) -> None:
        if not secret.get_secret_value():
            raise ValueError("the webhook secret must not be empty")
        self._key = secret.get_secret_value().encode()

    def matches(self, body: bytes, header: str | None) -> bool:
        if header is None or not header.startswith(SIGNATURE_PREFIX):
            return False
        expected = hmac.new(self._key, body, hashlib.sha256).hexdigest().encode()
        return hmac.compare_digest(expected, header.removeprefix(SIGNATURE_PREFIX).encode())
