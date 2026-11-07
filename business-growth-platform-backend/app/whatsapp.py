"""WhatsApp Cloud API foundation. No automatic sends or public routes are enabled here."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime

import httpx


class WhatsAppAPIError(Exception):
    """A redacted provider failure suitable for a future API response."""


class WhatsAppDeliveryUncertain(WhatsAppAPIError):
    """A send may have happened; callers must inspect delivery rather than blindly retry."""


def valid_webhook_signature(body: bytes, signature: str, app_secret: str) -> bool:
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(app_secret and signature) and hmac.compare_digest(expected, signature)


def event_time(value) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), UTC).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def object_value(value) -> dict:
    return value if isinstance(value, dict) else {}


def object_rows(value) -> list[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def parse_events(payload: dict) -> list[dict]:
    """Normalize messages and delivery receipts, retaining only fields needed by the inbox."""
    if payload.get("object") != "whatsapp_business_account":
        return []
    events = []
    for entry in object_rows(payload.get("entry")):
        account = str(entry.get("id") or "")
        if not account.isdigit():
            continue
        for change in object_rows(entry.get("changes")):
            value = object_value(change.get("value"))
            phone = str(object_value(value.get("metadata")).get("phone_number_id") or "")
            if (
                change.get("field") != "messages"
                or value.get("messaging_product") != "whatsapp"
                or not phone.isdigit()
            ):
                continue
            for message in object_rows(value.get("messages")):
                sender = str(message.get("from") or "")
                when = event_time(message.get("timestamp"))
                message_id = message.get("id")
                if (
                    not sender.isdigit()
                    or not isinstance(message_id, str)
                    or not message_id
                    or not when
                ):
                    continue
                kind = message.get("type")
                if not isinstance(kind, str):
                    continue
                text, choice_id = "", None
                if kind == "text":
                    text = object_value(message.get("text")).get("body") or ""
                elif kind == "button":
                    button = object_value(message.get("button"))
                    text, choice_id = button.get("text") or "", button.get("payload")
                elif kind == "interactive":
                    interaction = object_value(message.get("interactive"))
                    choice = object_value(
                        interaction.get("button_reply") or interaction.get("list_reply")
                    )
                    text, choice_id = choice.get("title") or "", choice.get("id")
                if not isinstance(text, str):
                    continue
                events.append(
                    {
                        "kind": "incoming",
                        "account_id": account,
                        "phone_number_id": phone,
                        "provider_message_id": message_id,
                        "contact_wa_id": sender,
                        "occurred_at": when,
                        "message_type": kind,
                        "text": text,
                        "choice_id": choice_id if isinstance(choice_id, str) else None,
                        "event_key": hashlib.sha256(
                            f"{phone}:incoming:{message_id}".encode()
                        ).hexdigest(),
                    }
                )
            for status in object_rows(value.get("statuses")):
                message_id, state = status.get("id"), status.get("status")
                when = event_time(status.get("timestamp"))
                recipient = str(status.get("recipient_id") or "")
                if (
                    not isinstance(message_id, str)
                    or not message_id
                    or not isinstance(state, str)
                    or state not in {"sent", "delivered", "read", "failed"}
                    or not when
                    or not recipient.isdigit()
                ):
                    continue
                errors = object_rows(status.get("errors"))
                code = errors[0].get("code") if errors and isinstance(errors[0], dict) else None
                events.append(
                    {
                        "kind": "delivery",
                        "account_id": account,
                        "phone_number_id": phone,
                        "provider_message_id": message_id,
                        "contact_wa_id": recipient,
                        "occurred_at": when,
                        "delivery_status": state,
                        "error_code": code if isinstance(code, int) else None,
                        "event_key": hashlib.sha256(
                            f"{phone}:{message_id}:{state}:{when}".encode()
                        ).hexdigest(),
                    }
                )
    return events


class WhatsAppClient:
    def __init__(self, version: str, http_client: httpx.AsyncClient | None = None):
        if not re.fullmatch(r"v\d{1,2}\.\d{1,2}", version):
            raise ValueError("Choose a valid Meta Graph API version")
        self.base_url = f"https://graph.facebook.com/{version}"
        self.http_client = http_client

    async def _request(self, method: str, path: str, token: str, **kwargs) -> dict:
        async def send(client):
            return await client.request(
                method,
                f"{self.base_url}/{path}",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )

        try:
            if self.http_client:
                response = await send(self.http_client)
            else:
                async with httpx.AsyncClient(timeout=25) as client:
                    response = await send(client)
        except httpx.HTTPError as exc:
            if method == "POST":
                raise WhatsAppDeliveryUncertain(
                    "WhatsApp delivery is unconfirmed. Check delivery activity before retrying."
                ) from exc
            raise WhatsAppAPIError("WhatsApp did not respond. Please try loading again.") from exc
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("Invalid response object")
        except (ValueError, TypeError) as exc:
            if method == "POST" and response.is_success:
                raise WhatsAppDeliveryUncertain(
                    "WhatsApp returned an unreadable send result. Check delivery before retrying."
                ) from exc
            raise WhatsAppAPIError("WhatsApp returned an unreadable result.") from exc
        if not response.is_success or body.get("error"):
            # Never expose provider error strings, which may echo tokens or submitted text.
            raise WhatsAppAPIError(f"WhatsApp rejected the request (HTTP {response.status_code}).")
        return body

    async def phone_details(self, phone_number_id: str, token: str) -> dict:
        if not phone_number_id.isdigit():
            raise ValueError("Invalid WhatsApp phone number ID")
        return await self._request(
            "GET",
            phone_number_id,
            token,
            params={"fields": "id,display_phone_number,verified_name"},
        )

    async def send_text(self, phone_number_id: str, recipient: str, text: str, token: str) -> str:
        if (
            not phone_number_id.isdigit()
            or not re.fullmatch(r"\d{7,15}", recipient)
            or not text.strip()
            or len(text) > 1000
        ):
            raise ValueError(
                "Choose a valid phone number, recipient and reply of 1–1000 characters"
            )
        result = await self._request(
            "POST",
            f"{phone_number_id}/messages",
            token,
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"body": text},
            },
        )
        messages = object_rows(result.get("messages"))
        if not messages or not isinstance(messages[0].get("id"), str) or not messages[0]["id"]:
            raise WhatsAppDeliveryUncertain(
                "WhatsApp did not return a message ID. Check delivery before retrying."
            )
        return messages[0]["id"]


def decode_verified_webhook(body: bytes, signature: str, app_secret: str) -> list[dict]:
    if len(body) > 1024 * 1024:
        raise ValueError("WhatsApp webhook exceeds the intake limit")
    if not valid_webhook_signature(body, signature, app_secret):
        raise ValueError("Invalid WhatsApp webhook signature")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise TypeError("Invalid WhatsApp webhook object")
    return parse_events(payload)
