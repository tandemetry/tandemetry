import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from tandemetry.ingest.github.auth import AppTokenProvider
from tandemetry.ingest.github.transport import GitHubTransport

START = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
CLIENT_ID = "Iv1.8a61f9b3a7aba766"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = SecretStr(
    KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class TokenEndpoint:
    def __init__(self) -> None:
        self.issued = 0
        self.authorizations: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.issued += 1
        self.authorizations.append(request.headers["Authorization"])
        return httpx.Response(
            201, json={"token": f"ghs_{self.issued}", "expires_at": "2026-11-21T13:00:00Z"}
        )


def tokens_at(clock: Clock, endpoint: TokenEndpoint, moments: list[timedelta]) -> list[str]:
    async def run() -> list[str]:
        async with httpx.AsyncClient(
            base_url="https://api.github.test", transport=httpx.MockTransport(endpoint)
        ) as http:
            provider = AppTokenProvider(CLIENT_ID, PEM, GitHubTransport(http, clock), clock)
            issued = []
            for moment in moments:
                clock.now = START + moment
                issued.append(await provider.token(1))
            return issued

    return asyncio.run(run())


def test_app_jwt_is_signed_by_the_app_key_and_backdated() -> None:
    clock = Clock()
    endpoint = TokenEndpoint()
    tokens_at(clock, endpoint, [timedelta(0)])
    claims = jwt.decode(
        endpoint.authorizations[0].removeprefix("Bearer "),
        KEY.public_key(),
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims == {
        "iss": CLIENT_ID,
        "iat": int((START - timedelta(seconds=60)).timestamp()),
        "exp": int((START + timedelta(minutes=9)).timestamp()),
    }


def test_installation_token_is_cached_until_close_to_expiry() -> None:
    endpoint = TokenEndpoint()
    issued = tokens_at(
        Clock(), endpoint, [timedelta(0), timedelta(minutes=54), timedelta(minutes=56)]
    )
    assert issued == ["ghs_1", "ghs_1", "ghs_2"]
