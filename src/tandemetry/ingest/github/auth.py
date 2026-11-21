from datetime import datetime, timedelta

import jwt
from pydantic import SecretStr, ValidationError

from tandemetry.ingest.github.ports import GitHubApiError
from tandemetry.ingest.github.rest import InstallationToken
from tandemetry.ingest.github.transport import Clock, GitHubTransport, utc_now

JWT_BACKDATE = timedelta(seconds=60)
JWT_LIFETIME = timedelta(minutes=9)
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)


class AppTokenProvider:
    """Installation access tokens of a GitHub App, cached per installation until near expiry."""

    def __init__(
        self,
        client_id: str,
        private_key: SecretStr,
        transport: GitHubTransport,
        clock: Clock = utc_now,
    ) -> None:
        self._client_id = client_id
        self._private_key = private_key
        self._transport = transport
        self._clock = clock
        self._tokens: dict[int, InstallationToken] = {}

    async def token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached is not None and cached.expires_at - TOKEN_REFRESH_MARGIN > self._clock():
            return cached.token
        response = await self._transport.send(
            "POST", f"/app/installations/{installation_id}/access_tokens", self.app_jwt()
        )
        try:
            fresh = InstallationToken.model_validate_json(response.content)
        except ValidationError:
            raise GitHubApiError("unexpected installation token response") from None
        self._tokens[installation_id] = fresh
        return fresh.token

    def app_jwt(self) -> str:
        now = self._clock()
        return jwt.encode(
            {
                "iat": _epoch(now - JWT_BACKDATE),
                "exp": _epoch(now + JWT_LIFETIME),
                "iss": self._client_id,
            },
            self._private_key.get_secret_value(),
            algorithm="RS256",
        )


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())
