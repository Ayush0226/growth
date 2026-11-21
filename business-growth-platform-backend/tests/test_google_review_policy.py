from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.google_review_policy import ReviewRule, ReviewSnapshot, evaluate_review


NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def decision(rule_changes=None, review_changes=None, **context):
    rule = ReviewRule(**{
        "workspace_id": "ours", "location_name": "accounts/a/locations/l",
        "enabled": True, "enabled_at": NOW - timedelta(days=1),
        "mode": "auto_publish", **(rule_changes or {}),
    })
    review = ReviewSnapshot(**{
        "workspace_id": "ours", "name": "accounts/a/locations/l/reviews/r",
        "rating": 5, "created_at": NOW - timedelta(hours=1),
        "updated_at": NOW - timedelta(minutes=10), **(review_changes or {}),
    })
    return evaluate_review(rule, review, **{
        "now": NOW, "connection_active": True, "delivery_owned": True,
        "reserved_today": 0, **context,
    })


def test_eligible_auto_mode_does_not_require_per_review_approval():
    assert decision().action == "auto_publish"


@pytest.mark.parametrize("mode", ["draft", "approval"])
def test_non_automatic_modes_remain_non_automatic(mode):
    assert decision({"mode": mode}).action == mode


@pytest.mark.parametrize("changes,reason", [
    ({"workspace_id": "another"}, "workspace_mismatch"),
    ({"name": "accounts/a/locations/other/reviews/r"}, "location_mismatch"),
    ({"has_reply": True}, "already_replied"),
    ({"rating": 1}, "rating_excluded"),
    ({"created_at": NOW - timedelta(days=2)}, "predates_activation"),
])
def test_excluded_reviews(changes, reason):
    result = decision(review_changes=changes)
    assert (result.action, result.reason) == ("skip", reason)


def test_old_review_edit_does_not_become_new_review():
    assert decision(review_changes={
        "created_at": NOW - timedelta(days=3), "updated_at": NOW,
    }).reason == "predates_activation"


def test_paused_rule_prevents_delivery():
    assert decision({"enabled": False}).reason == "rule_disabled"


@pytest.mark.parametrize("context,reason", [
    ({"connection_active": False}, "connection_inactive"),
    ({"delivery_owned": False}, "delivery_not_owned"),
    ({"delivery_state": "reserved"}, "delivery_reserved"),
    ({"delivery_state": "sent"}, "delivery_sent"),
    ({"delivery_state": "uncertain"}, "delivery_uncertain"),
])
def test_connection_ownership_and_duplicate_guards(context, reason):
    assert decision(**context).reason == reason


def test_blocked_terms_are_case_insensitive_and_blank_terms_ignored():
    assert decision({"blocked_terms": ["", "  REFUND  "]},
                    {"comment": "I requested a refund"}).reason == "blocked_term"
    assert decision({"blocked_terms": [" "]}).action == "auto_publish"


def test_review_edit_restarts_delay():
    result = decision({"delay_minutes": 20})
    assert result.action == "wait"
    assert result.eligible_at == NOW + timedelta(minutes=10)


def test_pending_reservations_count_against_daily_limit():
    assert decision({"daily_limit": 2}, reserved_today=2).reason == "daily_limit"


@pytest.mark.parametrize("changes", [
    {"enabled_at": None}, {"rating_min": 5, "rating_max": 2},
    {"enabled_at": NOW.replace(tzinfo=None)},
])
def test_invalid_rules_rejected(changes):
    with pytest.raises(ValidationError):
        decision(changes)


def test_naive_clock_rejected():
    with pytest.raises(ValueError):
        decision(now=NOW.replace(tzinfo=None))
