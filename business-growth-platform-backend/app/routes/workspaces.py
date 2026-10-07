from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.database import db, one
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, user: CurrentUser = Depends(current_user)) -> dict:
    existing = one(
        db()
        .table("workspace_members")
        .select("workspace_id")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if existing:
        return {"workspace_id": existing["workspace_id"], "created": False}
    try:
        result = (
            db()
            .rpc("create_workspace_for_user", {"workspace_name": payload.name, "owner_id": user.id})
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Workspace could not be created"
        ) from exc
    workspace_id = result.data
    return {"workspace_id": workspace_id, "created": True}
