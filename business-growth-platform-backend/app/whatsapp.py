"""WhatsApp Cloud API transport and signed event normalization."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime

import httpx


class WhatsAppAPIError(Exception):
    """A redacted provider failure suitable for a future API response."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


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
                        "pricing": object_value(status.get("pricing")),
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
            if method == "POST" and (response.is_success or response.status_code >= 500):
                raise WhatsAppDeliveryUncertain(
                    "WhatsApp returned an unreadable send result. Check delivery before retrying."
                ) from exc
            raise WhatsAppAPIError("WhatsApp returned an unreadable result.") from exc
        if method == "POST" and response.status_code >= 500:
            raise WhatsAppDeliveryUncertain(
                "WhatsApp delivery is unconfirmed. Check activity before retrying."
            )
        if not response.is_success or body.get("error"):
            # Never expose provider error strings, which may echo tokens or submitted text.
            code = object_value(body.get("error")).get("code")
            raise WhatsAppAPIError(
                f"WhatsApp rejected the request (HTTP {response.status_code}).",
                code if isinstance(code, int) else None,
            )
        return body

    async def rows(self, path: str, token: str, **params) -> list[dict]:
        result = []
        for _ in range(20):
            page = await self._request("GET", path, token, params={"limit": 100, **params})
            result.extend(object_rows(page.get("data")))
            paging = object_value(page.get("paging"))
            after = object_value(paging.get("cursors")).get("after")
            if not paging.get("next") or not after:
                return result
            params["after"] = after
        raise WhatsAppAPIError(
            "Too many account records. Contact support to narrow this connection."
        )

    async def validate_connection(
        self, waba: str, phone: str, token: str, app_id: str, app_secret: str
    ) -> dict:
        if not waba.isdigit() or not phone.isdigit():
            raise ValueError("Invalid WhatsApp account or phone ID")
        debug = await self._request(
            "GET", "debug_token", f"{app_id}|{app_secret}", params={"input_token": token}
        )
        data = object_value(debug.get("data"))
        scopes = set(data.get("scopes") or [])
        if (
            not data.get("is_valid")
            or str(data.get("app_id")) != app_id
            or not {"whatsapp_business_management", "whatsapp_business_messaging"}.issubset(scopes)
        ):
            raise WhatsAppAPIError(
                "Connection authorization or WhatsApp permissions are incomplete."
            )
        phones = await self.rows(
            f"{waba}/phone_numbers", token, fields="id,display_phone_number,verified_name"
        )
        match = next((p for p in phones if str(p.get("id")) == phone), None)
        if not match:
            raise WhatsAppAPIError(
                "The selected phone does not belong to the authorized WhatsApp account."
            )
        # Management access alone does not prove that this app is subscribed.
        await self._request("POST", f"{waba}/subscribed_apps", token)
        return match

    async def exchange_code(self, code: str, app_id: str, app_secret: str) -> str:
        body = await self._request(
            "GET",
            "oauth/access_token",
            f"{app_id}|{app_secret}",
            params={"client_id": app_id, "client_secret": app_secret, "code": code},
        )
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise WhatsAppAPIError("Meta did not return connection authorization.")
        return token

    async def templates(self, waba: str, token: str) -> list[dict]:
        if not waba.isdigit():
            raise ValueError("Invalid WhatsApp account ID")
        return await self.rows(
            f"{waba}/message_templates", token, fields="id,name,language,status,category,components"
        )

    async def create_template(self, waba: str, values: dict, token: str) -> dict:
        return await self._request("POST", f"{waba}/message_templates", token, json=values)

    async def send_template(
        self, phone: str, recipient: str, template: dict, parameters: list[str], token: str
    ) -> str:
        if not phone.isdigit() or not re.fullmatch(r"\d{7,15}", recipient):
            raise ValueError("Invalid WhatsApp number")
        payload = {"name": template["name"], "language": {"code": template["language"]}}
        if parameters:
            payload["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": value} for value in parameters],
                }
            ]
        result = await self._request(
            "POST",
            f"{phone}/messages",
            token,
            json={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": payload,
            },
        )
        messages = object_rows(result.get("messages"))
        if not messages or not messages[0].get("id"):
            raise WhatsAppDeliveryUncertain(
                "Delivery is unconfirmed. Check activity before retrying."
            )
        return messages[0]["id"]

    async def phone_details(self, phone_number_id: str, token: str) -> dict:
        if not phone_number_id.isdigit():
            raise ValueError("Invalid WhatsApp phone number ID")
        return await self._request(
            "GET",
            phone_number_id,
            token,
            params={"fields": "id,display_phone_number,verified_name"},
        )

    async def register_number(self, phone: str, pin: str, token: str):
        if not phone.isdigit() or not re.fullmatch(r"\d{6}", pin):
            raise ValueError("Invalid number or verification PIN")
        return await self._request(
            "POST", f"{phone}/register", token, json={"messaging_product": "whatsapp", "pin": pin}
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
