import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.images import MAX_SOURCE_BYTES, prepare_image


def original(format="PNG", size=(1800, 2250), color=(255, 0, 0, 0)):
    image = Image.new("RGBA", size, color)
    stream = io.BytesIO()
    image.convert("RGB").save(stream, format) if format == "JPEG" else image.save(stream, format)
    return stream.getvalue()


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_prepares_supported_original_as_bounded_jpeg(format):
    data, width, height = prepare_image(original(format))
    assert width == 1440 and height == 1800
    assert len(data) < 8 * 1024 * 1024
    with Image.open(io.BytesIO(data)) as result:
        assert result.format == "JPEG" and result.mode == "RGB"
        assert not result.getexif()


def test_transparent_pixels_become_white():
    data, _, _ = prepare_image(original(size=(400, 400)))
    with Image.open(io.BytesIO(data)) as image:
        assert all(channel > 245 for channel in image.getpixel((200, 200)))


@pytest.mark.parametrize(
    "content",
    [
        b"not an image",
        original(size=(100, 100)),
        original(size=(400, 1000)),
        b"x" * (MAX_SOURCE_BYTES + 1),
    ],
)
def test_invalid_or_out_of_bounds_original_is_rejected(content):
    with pytest.raises(HTTPException) as error:
        prepare_image(content)
    assert error.value.status_code == 422


def test_pixel_budget_checked_before_decode(monkeypatch):
    image = Image.new("RGB", (10, 10))
    image.format = "PNG"
    monkeypatch.setattr(type(image), "width", property(lambda self: 10000))
    monkeypatch.setattr(type(image), "height", property(lambda self: 10000))
    monkeypatch.setattr("app.images.Image.open", lambda *args: image)
    with pytest.raises(HTTPException, match="25 megapixels"):
        prepare_image(b"fixture")


def test_upload_middleware_rejects_oversize_before_route_reads_body():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from app.upload_limits import MediaUploadLimit

    app = FastAPI()
    app.add_middleware(MediaUploadLimit)
    calls = []

    @app.post("/api/media")
    async def upload(request: Request):
        calls.append(True)
        return {"bytes": len(await request.body())}

    with TestClient(app) as client:
        response = client.post(
            "/api/media",
            content=b"fixture",
            headers={"Content-Length": str(MAX_SOURCE_BYTES + 2 * 1024 * 1024)},
        )
        assert response.status_code == 413 and calls == []
        assert client.post("/api/media", content=b"fixture").status_code == 200


@pytest.mark.asyncio
async def test_upload_middleware_bounds_chunked_request():
    import httpx
    from fastapi import FastAPI, Request

    from app.upload_limits import MediaUploadLimit

    app = FastAPI()
    app.add_middleware(MediaUploadLimit)

    @app.post("/api/media")
    async def upload(request: Request):
        return {"bytes": len(await request.body())}

    async def chunks():
        for _ in range(23):
            yield b"x" * 1024 * 1024

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://fixture"
    ) as client:
        response = await client.post("/api/media", content=chunks())
        assert response.status_code == 413
