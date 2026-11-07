import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr

from app.access import access_state
from app.config import Settings, get_settings
from app.database import db
from app.security import CurrentUser, authenticated_user

router = APIRouter(prefix="/api/access", tags=["pilot access"])


@router.get("")
def status(
    user: CurrentUser = Depends(authenticated_user), settings: Settings = Depends(get_settings)
):
    allowed, ready, revoked = access_state(user.id)
    return {
        "approved": allowed,
        "setup_ready": ready
        and bool(settings.pilot_access_code and settings.pilot_access_code.get_secret_value()),
        "revoked": revoked,
    }


class AccessInput(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=128)


@router.post("/redeem")
def redeem(
    payload: AccessInput,
    user: CurrentUser = Depends(authenticated_user),
    settings: Settings = Depends(get_settings),
):
    allowed, ready, revoked = access_state(user.id)
    if allowed:
        return {"approved": True}
    if revoked:
        raise HTTPException(
            403, "Access has been withdrawn for this account. Contact the administrator."
        )
    if (
        not ready
        or not settings.pilot_access_code
        or not settings.pilot_access_code.get_secret_value()
    ):
        raise HTTPException(
            503, "Access setup is being completed. Please contact the administrator."
        )
    reserved = db().rpc("reserve_pilot_access_attempt", {"p_user": user.id}).execute().data
    if not reserved:
        raise HTTPException(
            429,
            "Too many attempts. Please wait 15 minutes before trying again.",
            headers={"Retry-After": "900"},
        )
    expected = settings.pilot_access_code.get_secret_value().encode()
    supplied = payload.code.get_secret_value().encode()
    if not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, "That access code is incorrect. Please try again.")
    # Conditional insert cannot overwrite an explicit revocation made concurrently.
    db().table("pilot_access_grants").upsert(
        {"user_id": user.id, "source": "access_code", "granted_at": datetime.now(UTC).isoformat()},
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()
    approved, _, _ = access_state(user.id)
    if not approved:
        raise HTTPException(403, "Access could not be approved. Contact the administrator.")
    return {"approved": True}
