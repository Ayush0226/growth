from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.images import MAX_SOURCE_BYTES


class MediaUploadLimit:
    """Limit multipart bytes before the parser spools them to disk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in {"/api/media", "/api/gbp/media/upload"}:
            return await self.app(scope, receive, send)
        source_limit = 8 * 1024 * 1024 if scope.get("path") == "/api/gbp/media/upload" else MAX_SOURCE_BYTES
        upload_error = "Choose an image no larger than 8 MB" if source_limit != MAX_SOURCE_BYTES else "Choose an image no larger than 20 MB"
        limit = source_limit + 1024 * 1024  # Allow multipart framing.
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid upload length"}, 400)(
                scope, receive, send
            )
        if declared > limit:
            return await JSONResponse({"detail": upload_error}, 413)(
                scope, receive, send
            )
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, upload_error)
            return message

        return await self.app(scope, bounded_receive, send)
