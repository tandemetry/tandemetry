from typing import Annotated

from aiokafka.errors import KafkaError
from fastapi import Depends, FastAPI, Header, Request, Response, status

from tandemetry.ingest.github.mapper import InvalidWebhookError
from tandemetry.ingest.github.receiver import InvalidSignatureError, Receipt, WebhookReceiver

RECEIPT_STATUS = {
    Receipt.ACCEPTED: status.HTTP_202_ACCEPTED,
    Receipt.IGNORED: status.HTTP_204_NO_CONTENT,
}


def get_receiver(request: Request) -> WebhookReceiver:
    receiver: WebhookReceiver = request.app.state.receiver
    return receiver


async def read_body(request: Request, limit: int) -> bytes | None:
    """The request body, or `None` once it is known to exceed `limit` bytes."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return None
    return bytes(body)


def create_app(receiver: WebhookReceiver, max_body_bytes: int) -> FastAPI:
    """The HTTP API: GitHub webhook intake and a liveness probe."""
    app = FastAPI(title="Tandemetry", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.receiver = receiver

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        receiver: Annotated[WebhookReceiver, Depends(get_receiver)],
        x_github_event: Annotated[str, Header()] = "",
        x_github_delivery: Annotated[str, Header()] = "",
        x_hub_signature_256: Annotated[str | None, Header()] = None,
    ) -> Response:
        body = await read_body(request, max_body_bytes)
        if body is None:
            return Response(status_code=status.HTTP_413_CONTENT_TOO_LARGE)
        try:
            receipt = await receiver.receive(
                x_github_event, x_github_delivery, x_hub_signature_256, body
            )
        except InvalidSignatureError:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        except InvalidWebhookError:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        except KafkaError:
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(status_code=RECEIPT_STATUS[receipt])

    return app
