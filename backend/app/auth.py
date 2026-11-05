from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User


bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_text, hash_text = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(hash_text)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(user: User, lifetime: timedelta = timedelta(hours=8), *, auth_provider: str = "password") -> str:
    payload = {"sub": user.id, "role": user.role, "name": user.full_name, "exp": int(time.time() + lifetime.total_seconds())}
    payload["auth_provider"] = auth_provider
    if auth_provider == "google":
        payload["google_sub"] = user.google_sub
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            raise ValueError("Expired")
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = decode_token(credentials.credentials)
    user = db.get(User, int(payload["sub"]))
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
    if settings.deped_only or user.google_email:
        if (payload.get("auth_provider") != "google" or not user.google_sub
                or payload.get("google_sub") != user.google_sub
                or not user.google_email or user.google_email.split("@")[-1] != "deped.gov.ph"):
            raise HTTPException(status_code=401, detail="Please sign in with your DepEd Google account")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Password change required before using EduScan")
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This role is not authorized")
        return user
    return dependency


def seed_users(db: Session) -> None:
    defaults = [
        ("admin", "admin123", "admin", "System Administrator"),
        ("teacher", "teacher123", "teacher", "Teacher Account"),
        ("scanner", "scanner123", "scanner", "Gate Scanner Device"),
    ]
    changed = False
    for username, password, role, full_name in defaults:
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, password_hash=hash_password(password), role=role, full_name=full_name,
                        must_change_password=True, failed_login_count=0))
            changed = True
    if changed:
        db.commit()
