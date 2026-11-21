"""Side-effect-free eligibility checks for the upcoming Google review worker.

This is not a delivery lock: the worker must reserve quota and delivery atomically,
fetch the authoritative review, and repeat these checks immediately before sending.
No routes or scheduled workers activate this module yet.
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class ReviewRule(BaseModel):
    workspace_id: str = Field(min_length=1)
    location_name: str = Field(pattern=r"^accounts/[^/]+/locations/[^/]+$")
    enabled: bool = False
    mode: Literal["draft", "approval", "auto_publish"] = "draft"
    enabled_at: AwareDatetime | None = None
    rating_min: int = Field(default=4, ge=1, le=5)
    rating_max: int = Field(default=5, ge=1, le=5)
    delay_minutes: int = Field(default=0, ge=0, le=10080)
    daily_limit: int = Field(default=20, ge=1, le=1000)
    blocked_terms: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_rule(self):
        if self.rating_min > self.rating_max:
            raise ValueError("Minimum rating cannot exceed maximum rating")
        if self.enabled and self.enabled_at is None:
            raise ValueError("Enabling a rule requires its activation timestamp")
        self.blocked_terms = list(dict.fromkeys(
            term.strip().casefold() for term in self.blocked_terms if term.strip()
        ))
        return self


class ReviewSnapshot(BaseModel):
    workspace_id: str = Field(min_length=1)
    name: str = Field(pattern=r"^accounts/[^/]+/locations/[^/]+/reviews/[^/]+$")
    rating: int = Field(ge=1, le=5)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    comment: str = ""
    has_reply: bool = False

    @model_validator(mode="after")
    def validate_timestamps(self):
        if self.updated_at < self.created_at:
            raise ValueError("Review update cannot precede creation")
        return self


class ReviewDecision(BaseModel):
    action: Literal["skip", "wait", "draft", "approval", "auto_publish"]
    reason: str
    eligible_at: AwareDatetime | None = None


def evaluate_review(
    rule: ReviewRule,
    review: ReviewSnapshot,
    *,
    now: datetime,
    connection_active: bool,
    delivery_owned: bool,
    reserved_today: int,
    delivery_state: Literal["new", "reserved", "sent", "uncertain"] = "new",
) -> ReviewDecision:
    """Evaluate trusted server-side snapshots; never accept ownership from clients.

    reserved_today includes pending reservations, not just completed sends. The
    eventual database reservation must enforce the same limit under concurrency.
    An uncertain send requires provider reconciliation, never automatic retry.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if reserved_today < 0:
        raise ValueError("Reserved count cannot be negative")
    reason = None
    if review.workspace_id != rule.workspace_id:
        reason = "workspace_mismatch"
    elif review.name.rsplit("/reviews/", 1)[0] != rule.location_name:
        reason = "location_mismatch"
    elif not rule.enabled:
        reason = "rule_disabled"
    elif not connection_active:
        reason = "connection_inactive"
    elif not delivery_owned:
        reason = "delivery_not_owned"
    elif delivery_state != "new":
        reason = f"delivery_{delivery_state}"
    elif review.has_reply:
        reason = "already_replied"
    elif rule.enabled_at is None or review.created_at < rule.enabled_at:
        reason = "predates_activation"
    elif not rule.rating_min <= review.rating <= rule.rating_max:
        reason = "rating_excluded"
    elif any(term in review.comment.casefold() for term in rule.blocked_terms):
        reason = "blocked_term"
    if reason:
        return ReviewDecision(action="skip", reason=reason)
    # Edits restart the quiet period so a queued reply cannot use stale content.
    eligible_at = review.updated_at + timedelta(minutes=rule.delay_minutes)
    if eligible_at > now:
        return ReviewDecision(action="wait", reason="delay_pending", eligible_at=eligible_at)
    if reserved_today >= rule.daily_limit:
        return ReviewDecision(action="wait", reason="daily_limit")
    return ReviewDecision(action=rule.mode, reason="eligible", eligible_at=eligible_at)
