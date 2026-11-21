import hashlib
import hmac

import pytest
from pydantic import SecretStr

from tandemetry.ingest.github.signature import WebhookSignature

GITHUB_DOCS_KEY = "It's a Secret to Everybody"
BODY = b"Hello, World!"
GITHUB_DOCS_SIGNATURE = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"


@pytest.fixture
def signature() -> WebhookSignature:
    return WebhookSignature(SecretStr(GITHUB_DOCS_KEY))


def test_signature_from_github_docs_matches(signature: WebhookSignature) -> None:
    assert signature.matches(BODY, GITHUB_DOCS_SIGNATURE)


@pytest.mark.parametrize(
    ("body", "header"),
    [
        (BODY + b" ", GITHUB_DOCS_SIGNATURE),
        (BODY, None),
        (BODY, GITHUB_DOCS_SIGNATURE.removeprefix("sha256=")),
        (BODY, "sha256=not-hex"),
        (BODY, "sha256=\xe9"),
        (BODY, "sha1=" + hashlib.sha1(BODY).hexdigest()),  # noqa: S324
        (BODY, "sha256=" + hmac.new(b"other", BODY, hashlib.sha256).hexdigest()),
    ],
)
def test_tampered_missing_or_foreign_signature_does_not_match(
    signature: WebhookSignature, body: bytes, header: str | None
) -> None:
    assert not signature.matches(body, header)


def test_empty_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        WebhookSignature(SecretStr(""))
