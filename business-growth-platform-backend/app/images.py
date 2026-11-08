"""Prepare supported originals for Instagram without changing their framing."""

import io

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_PUBLISHED_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 25_000_000
FORMATS = {"JPEG", "PNG", "WEBP"}


def prepare_image(content: bytes) -> tuple[bytes, int, int]:
    if len(content) > MAX_SOURCE_BYTES:
        raise HTTPException(422, "Choose an image no larger than 20 MB")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in FORMATS:
                raise HTTPException(422, "Choose a JPEG, PNG or WebP image")
            if source.width * source.height > MAX_PIXELS:
                raise HTTPException(422, "Choose an image with no more than 25 megapixels")
            if getattr(source, "is_animated", False):
                raise HTTPException(422, "Animated images are not supported; choose a still image")
            source.load()
            ImageOps.exif_transpose(source, in_place=True)
            image = source
            width, height = image.size
            if min(width, height) < 320:
                raise HTTPException(422, "Image dimensions must be at least 320 × 320 pixels")
            if not 0.8 <= width / height <= 1.91:
                raise HTTPException(
                    422, "Use proportions from 4:5 to 1.91:1, or choose an image fit in Create"
                )
            image.thumbnail((1440, 1800), Image.Resampling.LANCZOS)
            if image.mode != "RGB":
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            output = io.BytesIO()
            # No EXIF/location metadata or original filename is copied to the output.
            image.save(output, format="JPEG", quality=92, optimize=True)
            prepared = output.getvalue()
            if len(prepared) > MAX_PUBLISHED_BYTES:
                raise HTTPException(
                    422, "Image could not be prepared within Instagram's 8 MB limit"
                )
            return prepared, image.width, image.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "The uploaded image could not be opened safely") from exc
