import asyncio
import base64
import hashlib
import io
import json
import re
from uuid import uuid4

import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.database import db
from app.gbp import service

MAX_BYTES = 8*1024*1024


def normalize_photo(raw):
    # Ported from GBP Image Studio; never retain EXIF or the original filename.
    if len(raw)>MAX_BYTES:
        raise HTTPException(422, "Photos must be smaller than 8 MB")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"JPEG","PNG","WEBP"} or image.width*image.height>16_777_216 or getattr(image,"is_animated",False):
                raise ValueError()
            if min(image.size)<250:
                raise ValueError()
            image.load();image.thumbnail((2048,2048))
            converted=image.convert("RGB");output=io.BytesIO();converted.save(output,"JPEG",quality=92)
            return output.getvalue(),converted.width,converted.height
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(422,"Choose a valid JPEG, PNG or WebP photo, at least 250 pixels per side.") from None


def store_photo(ws, user, content, width, height):
    asset_id=str(uuid4());path=f"{ws}/{asset_id}.jpg"
    db().storage.from_("gbp-media").upload(path,content,{"content-type":"image/jpeg","upsert":"false"})
    rows=db().table("gbp_media_assets").insert({"id":asset_id,"workspace_id":ws,"created_by":user,
        "storage_path":path,"width":width,"height":height,"bytes":len(content)}).execute().data
    return rows[0]


async def generate_image(settings, ws, user, request_id, prompt):
    if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
        raise HTTPException(503,"Image generation is not configured.")
    if not re.fullmatch(r"[a-fA-F0-9]{32}",settings.cloudflare_account_id):
        raise HTTPException(503,"Image provider configuration is invalid.")
    fingerprint=hashlib.sha256(prompt.encode()).hexdigest()
    key=f"image:{ws}:{request_id}"
    claimed=await service.execute(db().table("gbp_operations").upsert({"operation_key":key,"workspace_id":ws,
        "result":{"fingerprint":fingerprint}},on_conflict="operation_key",ignore_duplicates=True))
    if not claimed:
        old=await service.execute(db().table("gbp_operations").select("*").eq("operation_key",key).eq("workspace_id",ws).limit(1))
        if old and old[0]["result"].get("fingerprint")==fingerprint and old[0]["status"]=="completed":
            return {"asset":old[0]["result"]["asset"],"replayed":True}
        raise HTTPException(409,"This image request has already been attempted. Inspect the media library before another request.")
    try:
        url=f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
        async with httpx.AsyncClient(timeout=90,follow_redirects=False) as http:
            async with http.stream("POST",url,headers={"Authorization":"Bearer "+settings.cloudflare_api_token.get_secret_value()},
                                   files={"prompt":(None,prompt),"width":(None,"1024"),"height":(None,"1024")}) as response:
                if not response.is_success:
                    raise ValueError()
                data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>MAX_BYTES*2:
                        raise ValueError()
                raw=bytes(data)
                if "json" in response.headers.get("content-type",""):
                    raw=base64.b64decode(json.loads(raw)["result"]["image"],validate=True)
        photo,width,height=await asyncio.to_thread(normalize_photo,raw)
        asset=await asyncio.to_thread(store_photo,ws,user,photo,width,height)
        await service.execute(db().table("gbp_operations").update({"status":"completed","result":{"fingerprint":fingerprint,"asset":asset}}).eq("operation_key",key))
        return {"asset":asset,"replayed":False}
    except Exception:
        await service.execute(db().table("gbp_operations").update({"status":"uncertain"}).eq("operation_key",key))
        raise HTTPException(502,"Image generation or saving is unconfirmed. Inspect the media library; this request will not retry automatically.") from None
