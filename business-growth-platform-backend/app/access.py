"""Persistent pilot access; all decisions stay on the trusted backend."""

from postgrest.exceptions import APIError

from app.database import db, one


def access_state(user_id: str) -> tuple[bool, bool, bool]:
    """Return (allowed, database_ready, explicitly_revoked)."""
    try:
        grant = one(
            db().table("pilot_access_grants").select("revoked_at").eq("user_id", user_id).execute()
        )
        return (
            bool(grant and not grant.get("revoked_at")),
            True,
            bool(grant and grant.get("revoked_at")),
        )
    except APIError as exc:
        if exc.code not in {"PGRST205", "42P01"}:
            raise
        # Keep the existing owner operational during deployment before the migration.
        # This fallback disappears as soon as the access table exists.
        member = one(
            db().table("workspace_members").select("id").eq("user_id", user_id).limit(1).execute()
        )
        return bool(member), False, False
