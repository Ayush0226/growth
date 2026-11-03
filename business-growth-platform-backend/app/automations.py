"""Authenticated webhook intake and durable, opt-in Instagram reply automation."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta

import httpx

from app.config import Settings
from app.database import db, one
from app.meta import InstagramClient, MetaAPIError
from app.security import TokenCipher


def valid_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(secret and signature) and hmac.compare_digest(expected, signature)


def matches_keyword(text: str, keywords: list[str]) -> bool:
    folded = text.casefold()
    return any(
        re.search(r"(?<!\w)" + re.escape(word.strip().casefold()) + r"(?!\w)", folded)
        for word in keywords
        if word.strip()
    )


def timestamp(value) -> str:
    number = float(value)
    if number > 10**11:
        number /= 1000
    return datetime.fromtimestamp(number, UTC).isoformat()


def parse_events(payload: dict) -> list[dict]:
    """Ignore echoes, non-text notifications and unidentifiable/stale-shape events."""
    events = []
    if payload.get("object") != "instagram":
        return events
    for entry in payload.get("entry", []):
        account_id = str(entry.get("id", ""))
        for item in entry.get("messaging", []):
            message = item.get("message") or {}
            sender = str((item.get("sender") or {}).get("id", ""))
            recipient = str((item.get("recipient") or {}).get("id", ""))
            if (
                not message.get("mid")
                or not message.get("text")
                or message.get("is_echo")
                or message.get("is_deleted")
                or not sender
                or sender == account_id
                or recipient != account_id
                or not item.get("timestamp")
            ):
                continue
            events.append(
                {
                    "account_id": account_id,
                    "kind": "dm",
                    "sender_id": sender,
                    "event_key": "dm:" + str(message["mid"]),
                    "text": message["text"],
                    "occurred_at": timestamp(item["timestamp"]),
                }
            )
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            sender = str((value.get("from") or {}).get("id", ""))
            if (
                change.get("field") != "comments"
                or not value.get("id")
                or not sender
                or sender == account_id
                or not value.get("text")
                or not entry.get("time")
            ):
                continue
            events.append(
                {
                    "account_id": account_id,
                    "kind": "comment",
                    "sender_id": sender,
                    "event_key": "comment:" + str(value["id"]),
                    "comment_id": str(value["id"]),
                    "media_id": str((value.get("media") or {}).get("id", "")),
                    "text": value["text"],
                    "occurred_at": timestamp(entry["time"]),
                }
            )
    return events


def ingest(payload: dict) -> int:
    count = 0
    for event in parse_events(payload):
        accounts = (
            db()
            .table("social_accounts")
            .select("workspace_id,connection_id")
            .eq("provider_account_id", event["account_id"])
            .execute()
            .data
        )
        for account in accounts:
            connection = one(
                db()
                .table("social_connections")
                .select("id")
                .eq("id", account["connection_id"])
                .eq("status", "active")
                .execute()
            )
            if not connection:
                continue
            result = (
                db()
                .table("automation_events")
                .upsert(
                    {**event, **account},
                    on_conflict="connection_id,event_key",
                    ignore_duplicates=True,
                )
                .execute()
            )
            count += len(result.data or [])
    return count


def select_rule(event: dict, rules: list[dict], first_inbound: bool) -> dict | None:
    for rule in rules:
        if not rule["enabled"]:
            continue
        if event["kind"] == "comment":
            if (
                rule["trigger"] == "comment_keyword"
                and event.get("media_id") in rule["media_ids"]
                and matches_keyword(event["text"], rule["keywords"])
            ):
                return rule
        elif rule["trigger"] == "dm_keyword" and matches_keyword(event["text"], rule["keywords"]):
            return rule
    if event["kind"] == "dm" and first_inbound:
        return next((r for r in rules if r["enabled"] and r["trigger"] == "welcome"), None)
    return None


async def process_event(event: dict, settings: Settings) -> None:
    claimed = (
        db()
        .table("automation_events")
        .update({"status": "processing"})
        .eq("id", event["id"])
        .eq("status", "pending")
        .execute()
        .data
    )
    if not claimed:
        return

    def finish(status: str, detail: str):
        db().table("automation_events").update(
            {"status": status, "detail": detail, "processed_at": datetime.now(UTC).isoformat()}
        ).eq("id", event["id"]).execute()

    now = datetime.now(UTC)
    cutoff = now - (timedelta(hours=24) if event["kind"] == "dm" else timedelta(days=7))
    occurred = datetime.fromisoformat(event["occurred_at"])
    if occurred < cutoff or occurred > now + timedelta(minutes=5):
        finish("ignored", "Outside the permitted response window")
        return
    connection = one(
        db()
        .table("social_connections")
        .select("*")
        .eq("id", event["connection_id"])
        .eq("workspace_id", event["workspace_id"])
        .eq("status", "active")
        .execute()
    )
    if not connection or "instagram_business_manage_messages" not in connection["granted_scopes"]:
        finish("ignored", "Instagram disconnected or messaging permission missing")
        return
    if (
        connection.get("active_account_id")
        and connection["active_account_id"] != event["account_id"]
    ):
        finish("ignored", "Event belongs to a previously connected account")
        return
    if (
        event["kind"] == "comment"
        and "instagram_business_manage_comments" not in connection["granted_scopes"]
    ):
        finish("ignored", "Comment permission missing")
        return
    first_inbound = False
    if event["kind"] == "dm":
        contact = {
            "workspace_id": event["workspace_id"],
            "connection_id": event["connection_id"],
            "sender_id": event["sender_id"],
            "first_event_id": event["id"],
            "last_inbound_at": event["occurred_at"],
        }
        db().table("automation_contacts").upsert(
            contact, on_conflict="connection_id,sender_id", ignore_duplicates=True
        ).execute()
        saved = one(
            db()
            .table("automation_contacts")
            .select("*")
            .eq("connection_id", event["connection_id"])
            .eq("sender_id", event["sender_id"])
            .execute()
        )
        first_inbound = saved["first_event_id"] == event["id"]
        if occurred > datetime.fromisoformat(saved["last_inbound_at"]):
            db().table("automation_contacts").update({"last_inbound_at": event["occurred_at"]}).eq(
                "connection_id", event["connection_id"]
            ).eq("sender_id", event["sender_id"]).execute()
    rules = (
        db()
        .table("automation_rules")
        .select("*")
        .eq("workspace_id", event["workspace_id"])
        .eq("enabled", True)
        .order("created_at")
        .execute()
        .data
    )
    rule = select_rule(event, rules, first_inbound)
    if not rule:
        finish("ignored", "No enabled rule matched")
        return
    daily = (
        db()
        .table("automation_deliveries")
        .select("id", count="exact")
        .eq("rule_id", rule["id"])
        .in_("status", ["sending", "sent", "uncertain"])
        .gte("created_at", now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat())
        .execute()
    )
    if (daily.count or 0) >= rule["daily_limit"]:
        finish("ignored", "Rule daily limit reached")
        return
    recent = (
        db()
        .table("automation_deliveries")
        .select("id")
        .eq("rule_id", rule["id"])
        .eq("recipient_id", event["sender_id"])
        .eq("connection_id", event["connection_id"])
        .in_("status", ["sending", "sent", "uncertain"])
        .gte("created_at", (now - timedelta(minutes=rule["cooldown_minutes"])).isoformat())
        .limit(1)
        .execute()
        .data
    )
    if recent:
        finish("ignored", "Recipient cooldown is active")
        return
    key = "welcome:" + event["sender_id"] if rule["trigger"] == "welcome" else event["event_key"]
    delivery = one(
        db()
        .table("automation_deliveries")
        .upsert(
            {
                "workspace_id": event["workspace_id"],
                "connection_id": event["connection_id"],
                "rule_id": rule["id"],
                "event_id": event["id"],
                "recipient_id": event["sender_id"],
                "dedupe_key": key,
                "reply_text": rule["reply_text"],
            },
            on_conflict="connection_id,dedupe_key",
            ignore_duplicates=True,
        )
        .execute()
    )
    if not delivery:
        finish("ignored", "This event or welcome has already been handled")
        return
    # Recheck the opt-in immediately before crossing the public delivery boundary.
    enabled = one(db().table("automation_rules").select("enabled").eq("id", rule["id"]).execute())
    active = one(
        db().table("social_connections").select("status").eq("id", event["connection_id"]).execute()
    )
    if not enabled or not enabled["enabled"] or not active or active["status"] != "active":
        db().table("automation_deliveries").update(
            {"status": "failed", "detail": "Rule disabled or account disconnected"}
        ).eq("id", delivery["id"]).execute()
        finish("ignored", "Rule disabled or account disconnected")
        return
    token = TokenCipher(settings.token_encryption_key).decrypt(connection["access_token_encrypted"])
    recipient = (
        {"comment_id": event["comment_id"]}
        if event["kind"] == "comment"
        else {"id": event["sender_id"]}
    )
    try:
        result = await InstagramClient(settings).post(
            f"{event['account_id']}/messages",
            token,
            recipient=json.dumps(recipient),
            message=json.dumps({"text": rule["reply_text"]}),
        )
    except httpx.HTTPError:
        db().table("automation_deliveries").update(
            {
                "status": "uncertain",
                "detail": "Delivery could not be confirmed. Check Instagram before sending again.",
            }
        ).eq("id", delivery["id"]).execute()
        finish("failed", "Uncertain delivery; no automatic retry")
        return
    except MetaAPIError:
        db().table("automation_deliveries").update(
            {
                "status": "failed",
                "detail": "Instagram rejected the reply. Check connection, permissions and message window.",
            }
        ).eq("id", delivery["id"]).execute()
        finish("failed", "Reply rejected; inspect Instagram before retrying")
        return
    db().table("automation_deliveries").update(
        {"status": "sent", "provider_message_id": result.get("message_id") or result.get("id")}
    ).eq("id", delivery["id"]).execute()
    finish("processed", "Reply sent")
