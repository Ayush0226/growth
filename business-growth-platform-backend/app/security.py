import hashlib
import secrets
from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status

from app.database import db


def generate_oauth_state() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_oauth_state(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class TokenCipher:
    def __init__(self, key: str):
        digest = hashlib.sha256(key.encode()).digest()
        self._fernet = Fernet(urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Stored token cannot be decrypted") from exc


class CurrentUser:
    def __init__(self, user_id: str, email: str | None):
        self.id = user_id
        self.email = email


def current_user(request: Request) -> CurrentUser:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = header.removeprefix("Bearer ").strip()
    try:
        response = db().auth.get_user(token)
        user = response.user
        if user is None:
            raise ValueError("Supabase returned no user")
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from exc
    return CurrentUser(str(user.id), user.email)
