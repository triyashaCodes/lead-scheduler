from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE = "Request body is too large"


class BodySizeLimitMiddleware:
    """Reject requests whose body exceeds `max_bytes`, before it is all read.

    Without this the server receives the entire upload before any handler can
    apply its own limit. A declared Content-Length over the limit is refused
    immediately; otherwise the bytes are counted as they arrive and the request
    is stopped as soon as the limit is passed (this also covers chunked bodies
    that declare no length).
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    break  # malformed; the byte count below still applies
                if declared > self.max_bytes:
                    response = JSONResponse({"detail": _TOO_LARGE}, status_code=413)
                    await response(scope, receive, send)
                    return
                break

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # An HTTPException is passed through by FastAPI's body
                    # parsing and turned into a normal 413 response.
                    raise HTTPException(status_code=413, detail=_TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)
