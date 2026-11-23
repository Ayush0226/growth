"""Normalize Business-app sync separately from live customer messages.

Reference: Meta, Onboard WhatsApp Business app users (23 November 2026).
No historical event is eligible for automation or a customer-service window.
"""

import hashlib
import json
import re

from app.whatsapp import event_time, object_rows, object_value


def normalize(account, phone, field, value):
    def event(kind, item):
        return {
            "kind": kind,
            "account_id": account,
            "phone_number_id": phone,
            **item,
            "event_key": hashlib.sha256(
                json.dumps([phone, field, kind, item], sort_keys=True).encode()
            ).hexdigest(),
        }

    def message(item, recipient, outbound, history):
        when = event_time(item.get("timestamp"))
        if not re.fullmatch(r"\d{7,15}", str(recipient or "")):
            return event(
                "sync_warning",
                {"detail": "An identity without a supported phone number was not imported."},
            )
        if not when or not isinstance(item.get("id"), str):
            return None
        text = object_value(item.get("text")).get("body", "")
        return event(
            "history_message" if history else "app_echo",
            {
                "contact_wa_id": recipient,
                "provider_message_id": item["id"],
                "direction": "outbound" if outbound else "inbound",
                "occurred_at": when,
                "message_type": str(item.get("type", "unknown"))[:50],
                "text": text[:4096] if isinstance(text, str) else "",
            },
        )

    result = []
    if field == "smb_message_echoes":
        for item in object_rows(value.get("message_echoes")):
            row = message(item, item.get("to"), True, False)
            if row:
                result.append(row)
    elif field == "history":
        for chunk in object_rows(value.get("history")):
            errors = object_rows(chunk.get("errors"))
            if errors:
                result.append(
                    event(
                        "history_progress",
                        {
                            "state": "declined"
                            if any(x.get("code") == 2593109 for x in errors)
                            else "error",
                            "progress": 0,
                        },
                    )
                )
                continue
            for thread in object_rows(chunk.get("threads")):
                for item in object_rows(thread.get("messages")):
                    result.append(
                        message(
                            item,
                            thread.get("id"),
                            str(item.get("from")) != str(thread.get("id")),
                            True,
                        )
                    )
            progress = object_value(chunk.get("metadata")).get("progress", 0)
            if (
                isinstance(progress, int)
                and not isinstance(progress, bool)
                and 0 <= progress <= 100
            ):
                result.append(
                    event(
                        "history_progress",
                        {
                            "state": "complete" if progress == 100 else "syncing",
                            "progress": progress,
                        },
                    )
                )
    elif field == "smb_app_state_sync":
        for item in object_rows(value.get("state_sync")):
            person = object_value(item.get("contact"))
            wa_id = str(person.get("phone_number") or "").lstrip("+")
            if item.get("type") != "contact" or item.get("action") not in {"add", "remove"}:
                continue
            if not re.fullmatch(r"\d{7,15}", wa_id):
                result.append(
                    event(
                        "sync_warning",
                        {"detail": "A contact without a supported phone number was not imported."},
                    )
                )
                continue
            result.append(
                event(
                    "contact_sync",
                    {
                        "contact_wa_id": wa_id,
                        "action": item["action"],
                        "name": str(person.get("full_name") or person.get("first_name") or "")[
                            :200
                        ],
                        "occurred_at": event_time(
                            object_value(item.get("metadata")).get("timestamp")
                        ),
                    },
                )
            )
    return [item for item in result if item]
