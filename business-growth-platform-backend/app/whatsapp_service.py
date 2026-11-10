"""Workspace-isolated WhatsApp inbox, campaigns and durable delivery processing."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from app.automations import matches_keyword
from app.chatbot import generate, human_request
from app.config import Settings
from app.database import db, one
from app.security import TokenCipher
from app.whatsapp import WhatsAppAPIError, WhatsAppClient, WhatsAppDeliveryUncertain

BILLING_URL = "https://business.facebook.com/latest/billing_hub/accounts"
PRICING_URL = "https://whatsappbusiness.com/resources/faq/"
PUBLIC_CONNECTION = (
    "id,status,waba_id,phone_number_id,display_phone_number,verified_name,connected_at,"
    "billing_acknowledged,ai_enabled,business_name,knowledge,instructions,handoff_message,"
    "ai_daily_limit,ai_enabled_at,updated_at"
)
STOP_WORDS = {"stop", "unsubscribe", "cancel", "stop messaging", "बंद करो"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def fingerprint(values) -> str:
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def available(settings: Settings):
    if not settings.whatsapp_enabled:
        raise HTTPException(503, "WhatsApp is being configured. Contact your administrator.")


def connection(workspace: str, *, private: bool = False, active: bool = True) -> dict:
    row = one(
        db()
        .table("whatsapp_connections")
        .select("*" if private else PUBLIC_CONNECTION)
        .eq("workspace_id", workspace)
        .execute()
    )
    if not row or (active and row["status"] != "active"):
        raise HTTPException(409, "Connect an active WhatsApp Business account first.")
    return row


def client_token(conn: dict, settings: Settings):
    return WhatsAppClient(settings.meta_graph_api_version), TokenCipher(
        settings.token_encryption_key
    ).decrypt(conn["access_token_encrypted"])


def contact(conn: dict, wa_id: str) -> dict | None:
    return one(
        db()
        .table("whatsapp_contacts")
        .select("*")
        .eq("connection_id", conn["id"])
        .eq("wa_id", wa_id)
        .execute()
    )


def service_window(conn: dict, wa_id: str) -> datetime | None:
    last = one(
        db()
        .table("whatsapp_messages")
        .select("occurred_at")
        .eq("connection_id", conn["id"])
        .eq("contact_wa_id", wa_id)
        .eq("direction", "inbound")
        .order("occurred_at", desc=True)
        .limit(1)
        .execute()
    )
    if not last:
        return None
    when = stamp(last["occurred_at"])
    now = datetime.now(UTC)
    return (
        when + timedelta(hours=24)
        if now - timedelta(hours=24) < when <= now + timedelta(minutes=5)
        else None
    )


def template_shape(item: dict) -> tuple[bool, int]:
    """Initial sender supports text bodies, static headers/footers/buttons, and positional fields."""
    components = item.get("components") or []
    body = next((c.get("text", "") for c in components if c.get("type") == "BODY"), "")
    indices = {int(n) for n in re.findall(r"\{\{(\d+)\}\}", body)}
    count = max(indices, default=0)
    supported = bool(body) and count <= 10 and indices == set(range(1, count + 1))
    if re.search(r"\{\{[^}]+\}\}", re.sub(r"\{\{\d+\}\}", "", body)):
        supported = False
    for component in components:
        if component.get("type") == "BODY":
            continue
        if (
            "{{" in json.dumps(component)
            or (component.get("type") == "HEADER" and component.get("format") != "TEXT")
            or component.get("type") not in {"HEADER", "FOOTER", "BUTTONS"}
        ):
            supported = False
    return supported and item.get("status") == "APPROVED", count


async def sync_templates(conn: dict, settings: Settings) -> list[dict]:
    client, token = client_token(conn, settings)
    rows = await client.templates(conn["waba_id"], token)
    # Mark old records unavailable before replacing the current provider snapshot.
    db().table("whatsapp_templates").update({"sendable": False, "status": "UNAVAILABLE"}).eq(
        "connection_id", conn["id"]
    ).execute()
    values = []
    for row in rows:
        supported, count = template_shape(row)
        values.append(
            {
                "id": row["id"],
                "workspace_id": conn["workspace_id"],
                "connection_id": conn["id"],
                "name": row["name"],
                "language": row["language"],
                "status": row["status"],
                "category": row["category"],
                "components": row.get("components", []),
                "sendable": supported,
                "parameter_count": count,
                "synced_at": now_iso(),
            }
        )
    if values:
        db().table("whatsapp_templates").upsert(values, on_conflict="connection_id,id").execute()
    return values


def queue_message(conn: dict, wa_id: str, request_id: str, text: str = "", **extra) -> dict:
    values = {
        "workspace_id": conn["workspace_id"],
        "connection_id": conn["id"],
        "contact_wa_id": wa_id,
        "direction": "outbound",
        "text": text,
        "request_id": request_id,
        "status": "queued",
        **extra,
    }
    request_hash = fingerprint({k: v for k, v in values.items() if k != "status"})
    db().table("whatsapp_messages").upsert(
        {**values, "request_hash": request_hash},
        on_conflict="workspace_id,request_id",
        ignore_duplicates=True,
    ).execute()
    row = one(
        db()
        .table("whatsapp_messages")
        .select("*")
        .eq("workspace_id", conn["workspace_id"])
        .eq("request_id", request_id)
        .execute()
    )
    if not row or row["request_hash"] != request_hash:
        raise HTTPException(409, "This request was already used for a different message.")
    return row


def ingest(events: list[dict]) -> int:
    inserted = 0
    for event in events:
        conn = one(
            db()
            .table("whatsapp_connections")
            .select("id,workspace_id,connected_at")
            .eq("phone_number_id", event["phone_number_id"])
            .eq("waba_id", event["account_id"])
            .eq("status", "active")
            .execute()
        )
        if not conn:
            continue
        result = (
            db()
            .table("whatsapp_events")
            .upsert(
                {
                    "workspace_id": conn["workspace_id"],
                    "connection_id": conn["id"],
                    "event_key": event["event_key"],
                    "event": event,
                },
                on_conflict="connection_id,event_key",
                ignore_duplicates=True,
            )
            .execute()
        )
        inserted += len(result.data or [])
    return inserted


def finish_event(event_id: str, state: str, detail: str = ""):
    db().table("whatsapp_events").update(
        {"status": state, "detail": detail, "processed_at": now_iso()}
    ).eq("id", event_id).execute()


def apply_receipt(conn: dict, item: dict) -> bool:
    row = one(
        db()
        .table("whatsapp_messages")
        .select("*")
        .eq("connection_id", conn["id"])
        .eq("provider_message_id", item["provider_message_id"])
        .eq("contact_wa_id", item["contact_wa_id"])
        .eq("direction", "outbound")
        .execute()
    )
    if not row:
        return False  # A receipt can precede the send HTTP response; leave it durable for the next pass.
    state = item["delivery_status"]
    rank = {
        "queued": 0,
        "sending": 0,
        "uncertain": 0,
        "failed": 0,
        "sent": 1,
        "delivered": 2,
        "read": 3,
    }
    values = {}
    if (state == "failed" and row["status"] not in {"delivered", "read"}) or rank.get(
        state, 0
    ) > rank.get(row["status"], 0):
        values["status"] = state
    if state in {"delivered", "read"} and not row.get("delivered_at"):
        values["delivered_at"] = item["occurred_at"]
    pricing = item.get("pricing") or {}
    if isinstance(pricing.get("billable"), bool):
        values["pricing_billable"] = pricing["billable"]
    if pricing.get("category") in {"service", "marketing", "utility", "authentication"}:
        values["category"] = pricing["category"]
    if pricing.get("type") in {"regular", "free_customer_service", "free_entry_point"}:
        values["pricing_type"] = pricing["type"]
    if item.get("error_code"):
        values["detail"] = (
            f"Meta delivery error {item['error_code']}. Check account billing and message eligibility."
        )
    if values:
        db().table("whatsapp_messages").update({**values, "updated_at": now_iso()}).eq(
            "id", row["id"]
        ).execute()
    return True


async def process_event(record: dict, settings: Settings):
    if (
        not db()
        .table("whatsapp_events")
        .update({"status": "processing", "claimed_at": now_iso()})
        .eq("id", record["id"])
        .eq("status", "pending")
        .execute()
        .data
    ):
        return
    conn = one(
        db()
        .table("whatsapp_connections")
        .select("*")
        .eq("id", record["connection_id"])
        .eq("workspace_id", record["workspace_id"])
        .eq("status", "active")
        .execute()
    )
    if not conn:
        finish_event(record["id"], "ignored", "Connection is inactive")
        return
    event = record["event"]
    if event["kind"] == "delivery":
        matched = apply_receipt(conn, event)
        if matched:
            finish_event(record["id"], "processed")
        elif stamp(record["received_at"]) < datetime.now(UTC) - timedelta(days=1):
            finish_event(
                record["id"], "ignored", "Receipt is not for a message captured by Growthboard"
            )
        else:
            db().table("whatsapp_events").update(
                {
                    "status": "pending",
                    "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                }
            ).eq("id", record["id"]).execute()
        return
    wa_id = event["contact_wa_id"]
    if not re.fullmatch(r"\d{7,15}", wa_id):
        finish_event(record["id"], "ignored", "Unsupported recipient")
        return
    db().table("whatsapp_contacts").upsert(
        {"workspace_id": conn["workspace_id"], "connection_id": conn["id"], "wa_id": wa_id},
        on_conflict="connection_id,wa_id",
        ignore_duplicates=True,
    ).execute()
    db().table("whatsapp_messages").upsert(
        {
            "workspace_id": conn["workspace_id"],
            "connection_id": conn["id"],
            "contact_wa_id": wa_id,
            "direction": "inbound",
            "provider_message_id": event["provider_message_id"],
            "message_type": event["message_type"],
            "text": event["text"][:4096],
            "status": "received" if event["text"] else "unsupported",
            "occurred_at": event["occurred_at"],
        },
        on_conflict="connection_id,provider_message_id",
        ignore_duplicates=True,
    ).execute()
    db().table("whatsapp_contacts").update({"updated_at": now_iso()}).eq(
        "connection_id", conn["id"]).eq("wa_id", wa_id).execute()
    person = contact(conn, wa_id)
    text = event["text"].strip()
    if text.casefold().strip(".! ") in STOP_WORDS:
        db().table("whatsapp_contacts").update(
            {
                "opted_out": True,
                "opted_in": False,
                "automation_paused": True,
                "updated_at": now_iso(),
            }
        ).eq("id", person["id"]).execute()
        finish_event(record["id"], "processed", "Opt-out recorded; messages suppressed")
        return
    if human_request(text):
        db().table("whatsapp_contacts").update(
            {"automation_paused": True, "updated_at": now_iso()}
        ).eq("id", person["id"]).execute()
        finish_event(record["id"], "processed", "Customer requested staff; automation paused")
        return
    if (
        not text
        or person["opted_out"]
        or person["automation_paused"]
        or not service_window(conn, wa_id)
    ):
        finish_event(
            record["id"], "ignored", "Unsupported content, paused contact or closed reply window"
        )
        return
    if stamp(event["occurred_at"]) < stamp(conn["connected_at"]):
        finish_event(record["id"], "ignored", "Message predates this connection")
        return
    rules = (
        db()
        .table("whatsapp_rules")
        .select("*")
        .eq("connection_id", conn["id"])
        .eq("enabled", True)
        .order("created_at")
        .execute()
        .data
    )
    inbound = (
        db()
        .table("whatsapp_messages")
        .select("id", count="exact")
        .eq("connection_id", conn["id"])
        .eq("contact_wa_id", wa_id)
        .eq("direction", "inbound")
        .limit(0)
        .execute()
    )
    eligible = [r for r in rules if stamp(event["occurred_at"]) >= stamp(r["updated_at"])]
    rule = next(
        (r for r in eligible if r["trigger"] == "keyword" and matches_keyword(text, r["keywords"])),
        None,
    )
    if not rule and inbound.count == 1:
        rule = next((r for r in eligible if r["trigger"] == "welcome"), None)
    reply, extra = "", {}
    if rule:
        day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        daily = (
            db()
            .table("whatsapp_messages")
            .select("id", count="exact")
            .eq("rule_id", rule["id"])
            .gte("created_at", day)
            .limit(0)
            .execute()
        )
        recent = one(
            db()
            .table("whatsapp_messages")
            .select("id")
            .eq("rule_id", rule["id"])
            .eq("contact_wa_id", wa_id)
            .gte(
                "created_at",
                (datetime.now(UTC) - timedelta(minutes=rule["cooldown_minutes"])).isoformat(),
            )
            .limit(1)
            .execute()
        )
        if (daily.count or 0) < rule["daily_limit"] and not recent:
            reply, extra = rule["reply_text"], {"rule_id": rule["id"]}
    elif (
        conn["ai_enabled"]
        and conn.get("ai_enabled_at")
        and stamp(event["occurred_at"]) >= stamp(conn["ai_enabled_at"])
    ):
        reserved = (
            db()
            .rpc(
                "wa_reserve_ai",
                {
                    "p_connection": conn["id"],
                    "p_event": record["id"],
                    "p_limit": conn["ai_daily_limit"],
                },
            )
            .execute()
            .data
        )
        if reserved:
            history = (
                db().table("whatsapp_messages").select("direction,text,status,provider_message_id")
            )
            history = (
                history.eq("connection_id", conn["id"])
                .eq("contact_wa_id", wa_id)
                .order("occurred_at", desc=True)
                .limit(9)
                .execute()
                .data
            )
            context = [
                {
                    "role": "user" if h["direction"] == "inbound" else "assistant",
                    "content": h["text"],
                }
                for h in reversed(history)
                if h["text"]
                and h.get("provider_message_id") != event["provider_message_id"]
                and h["status"] in {"received", "sent", "delivered", "read"}
            ]
            answer = await generate({**conn, "role": "support"}, text, settings, context)
            reply = answer["reply"]
            if answer["handoff"]:
                # Pause once this handoff message has been queued; permit that single message to send.
                extra["purpose"] = "handoff"
    if reply:
        queue_message(
            conn,
            wa_id,
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"wa:{record['id']}")),
            reply,
            event_id=record["id"],
            **{"purpose": "automation", **extra},
        )
    finish_event(
        record["id"], "processed", "Reply queued" if reply else "No eligible automation matched"
    )


async def deliver(row: dict, settings: Settings):
    recent = one(
        db()
        .table("whatsapp_messages")
        .select("id")
        .eq("connection_id", row["connection_id"])
        .eq("contact_wa_id", row["contact_wa_id"])
        .eq("direction", "outbound")
        .in_("status", ["sending", "sent", "delivered", "read", "uncertain"])
        .gte("updated_at", (datetime.now(UTC) - timedelta(seconds=6)).isoformat())
        .limit(1)
        .execute()
    )
    if recent:
        return  # Leave new work queued rather than violating Meta's per-recipient pacing.
    if (
        not db()
        .table("whatsapp_messages")
        .update({"status": "sending", "updated_at": now_iso()})
        .eq("id", row["id"])
        .eq("status", "queued")
        .execute()
        .data
    ):
        return

    def finish(state: str, detail: str, **values):
        db().table("whatsapp_messages").update(
            {"status": state, "detail": detail, "updated_at": now_iso(), **values}
        ).eq("id", row["id"]).eq("status", "sending").execute()

    conn = one(
        db()
        .table("whatsapp_connections")
        .select("*")
        .eq("id", row["connection_id"])
        .eq("workspace_id", row["workspace_id"])
        .eq("status", "active")
        .execute()
    )
    if not conn:
        finish("failed", "Connection inactive; no send attempted")
        return
    if not conn["billing_acknowledged"]:
        finish("failed", "Direct Meta charges have not been acknowledged; no send attempted")
        return
    if stamp(row["created_at"]) < stamp(conn["connected_at"]):
        finish("failed", "Message predates the renewed connection; no send attempted")
        return
    person = contact(conn, row["contact_wa_id"])
    if (
        not person
        or person["opted_out"]
        or (row["purpose"] in {"automation", "handoff"} and person["automation_paused"])
    ):
        finish("failed", "Contact opted out or automation is paused; no send attempted")
        return
    if row.get("rule_id"):
        rule = one(
            db()
            .table("whatsapp_rules")
            .select("*")
            .eq("id", row["rule_id"])
            .eq("connection_id", conn["id"])
            .eq("enabled", True)
            .execute()
        )
        if (
            not rule
            or row["text"] != rule["reply_text"]
            or stamp(row["created_at"]) < stamp(rule["updated_at"])
        ):
            finish("failed", "Rule was paused or changed; no send attempted")
            return
    if (
        row["purpose"] in {"automation", "handoff"}
        and not row.get("rule_id")
        and (
            not conn["ai_enabled"]
            or not conn.get("ai_enabled_at")
            or stamp(row["created_at"]) < stamp(conn["ai_enabled_at"])
        )
    ):
        finish("failed", "AI is paused; no send attempted")
        return
    template = row.get("template")
    if template:
        campaign = one(
            db()
            .table("whatsapp_campaigns")
            .select("status")
            .eq("id", row["campaign_id"])
            .eq("connection_id", conn["id"])
            .execute()
        )
        if (
            not campaign
            or campaign["status"] != "running"
            or not person["opted_in"]
            or not conn["billing_acknowledged"]
        ):
            finish(
                "failed",
                "Campaign paused, consent missing or billing not acknowledged; no send attempted",
            )
            return
    elif not service_window(conn, row["contact_wa_id"]):
        finish("failed", "The 24-hour service window is closed; use an approved template")
        return
    client, token = client_token(conn, settings)
    try:
        provider_id = (
            await client.send_template(
                conn["phone_number_id"], row["contact_wa_id"], template, row["parameters"], token
            )
            if template
            else await client.send_text(
                conn["phone_number_id"], row["contact_wa_id"], row["text"], token
            )
        )
    except WhatsAppDeliveryUncertain:
        finish(
            "uncertain",
            "Delivery unconfirmed. Inspect Meta activity; this message will not retry automatically.",
        )
        if row.get("campaign_id"):
            db().table("whatsapp_campaigns").update(
                {
                    "status": "paused",
                    "detail": "Delivery is uncertain. Review activity before resuming.",
                }
            ).eq("id", row["campaign_id"]).execute()
        return
    except WhatsAppAPIError as exc:
        finish(
            "failed",
            f"Meta rejected the send{f' (code {exc.code})' if exc.code else ''}. Check billing, permissions and eligibility.",
        )
        if row.get("campaign_id"):
            db().table("whatsapp_campaigns").update(
                {
                    "status": "paused",
                    "detail": "Meta rejected a message. Check billing and activity before resuming.",
                }
            ).eq("id", row["campaign_id"]).execute()
        return
    finish("sent", "Accepted by Meta; awaiting delivery receipt", provider_message_id=provider_id)
    if row["purpose"] == "handoff":
        db().table("whatsapp_contacts").update(
            {"automation_paused": True, "updated_at": now_iso()}
        ).eq("id", person["id"]).execute()


async def run_pending(settings: Settings, lost=None) -> dict:
    """Called inside the existing distributed worker lease. Never retries interrupted sends."""
    if not settings.whatsapp_enabled:
        return {"events": 0, "messages": 0}
    cutoff = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    interrupted = (
        db()
        .table("whatsapp_messages")
        .update(
            {
                "status": "uncertain",
                "detail": "Processing was interrupted. Inspect delivery before sending again.",
            }
        )
        .eq("status", "sending")
        .lt("updated_at", cutoff)
        .execute()
    )
    for campaign_id in {r["campaign_id"] for r in interrupted.data or [] if r.get("campaign_id")}:
        db().table("whatsapp_campaigns").update(
            {
                "status": "paused",
                "detail": "A send was interrupted. Inspect delivery activity before resuming remaining recipients.",
            }
        ).eq("id", campaign_id).eq("status", "running").execute()
    db().table("whatsapp_events").update(
        {"status": "failed", "detail": "Processing interrupted; no automatic replay"}
    ).eq("status", "processing").lt("claimed_at", cutoff).execute()
    result = {"events": 0, "messages": 0}
    events = (
        db()
        .table("whatsapp_events")
        .select("*")
        .eq("status", "pending")
        .lte("next_attempt_at", now_iso())
        .order("received_at")
        .limit(30)
        .execute()
        .data
    )
    for event in events:
        if lost and lost.is_set():
            return result
        try:
            await process_event(event, settings)
        except Exception:  # noqa: BLE001 - do not replay partially processed events or expose secrets
            finish_event(
                event["id"],
                "failed",
                "Processing failed. Inspect message activity before retrying.",
            )
        result["events"] += 1
    campaigns = (
        db()
        .table("whatsapp_campaigns")
        .select("*")
        .in_("status", ["scheduled", "running"])
        .lte("scheduled_for", now_iso())
        .order("created_at")
        .limit(5)
        .execute()
        .data
    )
    for campaign in campaigns:
        if lost and lost.is_set():
            return result
        conn = one(
            db()
            .table("whatsapp_connections")
            .select("*")
            .eq("id", campaign["connection_id"])
            .eq("workspace_id", campaign["workspace_id"])
            .eq("status", "active")
            .execute()
        )
        if not conn or not conn["billing_acknowledged"]:
            db().table("whatsapp_campaigns").update(
                {
                    "status": "paused",
                    "detail": "Connect WhatsApp and acknowledge direct Meta billing.",
                }
            ).eq("id", campaign["id"]).execute()
            continue
        if (
            stamp(campaign["scheduled_for"]) < datetime.now(UTC) - timedelta(days=1)
            and campaign["status"] == "scheduled"
        ):
            db().table("whatsapp_campaigns").update(
                {
                    "status": "paused",
                    "detail": "Schedule missed by more than a day. Review before resuming.",
                }
            ).eq("id", campaign["id"]).execute()
            continue
        try:
            templates = await sync_templates(conn, settings)
        except WhatsAppAPIError:
            continue  # A read can be retried without duplicating a public message.
        snapshot = campaign["template"]
        live = next((t for t in templates if t["id"] == snapshot["id"]), None)
        if (
            not live
            or not live["sendable"]
            or any(live[k] != snapshot[k] for k in ("name", "language", "category", "components"))
        ):
            db().table("whatsapp_campaigns").update(
                {
                    "status": "paused",
                    "detail": "Template changed or is no longer approved. Create a new reviewed campaign.",
                }
            ).eq("id", campaign["id"]).execute()
            continue
        current = (
            db()
            .table("whatsapp_campaigns")
            .update({"status": "running"})
            .eq("id", campaign["id"])
            .in_("status", ["scheduled", "running"])
            .execute()
            .data
        )
        if not current:
            continue
        existing = (
            db()
            .table("whatsapp_messages")
            .select("contact_wa_id")
            .eq("campaign_id", campaign["id"])
            .limit(1000)
            .execute()
            .data
        )
        already = {m["contact_wa_id"] for m in existing}
        for recipient in [r for r in campaign["recipients"] if r["wa_id"] not in already][:25]:
            queue_message(
                conn,
                recipient["wa_id"],
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"wa:{campaign['id']}:{recipient['wa_id']}")),
                "",
                purpose="campaign",
                message_type="template",
                category=snapshot["category"].lower(),
                template=snapshot,
                parameters=recipient["parameters"],
                campaign_id=campaign["id"],
            )
    rows = (
        db()
        .table("whatsapp_messages")
        .select("*")
        .eq("direction", "outbound")
        .eq("status", "queued")
        .is_("campaign_id", "null")
        .order("created_at")
        .limit(25)
        .execute()
        .data
    )
    running = (
        db()
        .table("whatsapp_campaigns")
        .select("id")
        .eq("status", "running")
        .limit(100)
        .execute()
        .data
    )
    if running and len(rows) < 25:
        rows.extend(
            db()
            .table("whatsapp_messages")
            .select("*")
            .eq("status", "queued")
            .in_("campaign_id", [c["id"] for c in running])
            .order("created_at")
            .limit(25 - len(rows))
            .execute()
            .data
        )
    for row in rows:
        if lost and lost.is_set():
            return result
        # A paused campaign keeps its queued recipients for an explicit resume.
        if row.get("campaign_id"):
            c = one(
                db()
                .table("whatsapp_campaigns")
                .select("status")
                .eq("id", row["campaign_id"])
                .execute()
            )
            if not c or c["status"] != "running":
                continue
        await deliver(row, settings)
        result["messages"] += 1
    for campaign in campaigns:
        stats = (
            db()
            .table("whatsapp_messages")
            .select("status")
            .eq("campaign_id", campaign["id"])
            .limit(1000)
            .execute()
            .data
        )
        if len(stats) == len(campaign["recipients"]) and all(
            m["status"] not in {"queued", "sending"} for m in stats
        ):
            db().table("whatsapp_campaigns").update({"status": "completed"}).eq(
                "id", campaign["id"]
            ).eq("status", "running").execute()
    return result
