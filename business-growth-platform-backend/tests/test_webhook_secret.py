import hashlib
import hmac

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_automations import settings  # noqa: F401 - shared fixture

from app.config import get_settings
from app.routes import engagement


def test_webhook_can_use_a_separate_meta_app_secret(monkeypatch, settings):  # noqa: F811 - injected pytest fixture
    settings.meta_webhook_app_secret = "separate-webhook-secret"
    app = FastAPI()
    app.include_router(engagement.router)
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(engagement, "ingest", lambda payload: 0)
    client = TestClient(app)
    body = b'{"object":"instagram","entry":[]}'

    def signed(secret):
        return {
            "x-hub-signature-256": "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        }

    assert (
        client.post(
            "/api/instagram/webhook", content=body, headers=signed(settings.meta_app_secret)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/instagram/webhook", content=body, headers=signed(settings.meta_webhook_app_secret)
        ).status_code
        == 200
    )
