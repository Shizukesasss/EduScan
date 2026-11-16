from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuthSession, User


DEPED_PASSWORD_PREFIX = "deped:"
DEPED_PASSWORD_PROVIDER = "deped_password"
SESSION_COOKIE = "eduscan_session"
SESSION_LIFETIME = timedelta(hours=8)
SESSION_REQUEST_HEADER = "X-EduScan-Request"
SESSION_CONTEXT_HEADER = "X-EduScan-Session-Context"
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


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


def has_deped_password(user: User) -> bool:
    return bool(user.google_sub and user.google_email and user.google_email.endswith("@deped.gov.ph")
                and user.password_hash.startswith(DEPED_PASSWORD_PREFIX))


def _password_stamp(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()


def require_app_request(request: Request) -> None:
    if request.headers.get(SESSION_REQUEST_HEADER) != "1":
        raise HTTPException(403, "Send this request from an authorized EduScan website")
    origin = request.headers.get("origin")
    if origin is not None:
        if origin in settings.allowed_origins:
            return
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host and origin in (f"https://{host}", f"http://{host}"):
            return
        origin_host = (urlsplit(origin).hostname or "").lower()
        if (os.getenv("VERCEL") or any("vercel.app" in o for o in settings.allowed_origins)) and origin_host.endswith(".vercel.app"):
            return
        raise HTTPException(403, "Send this request from an authorized EduScan website")


def secure_session_transport(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    origin = request.headers.get("origin")
    if (request.url.scheme == "http" and request.url.hostname in _LOOPBACK_HOSTS
            and request.client is not None and request.client.host in _LOOPBACK_HOSTS):
        if origin is None or urlsplit(origin).hostname in _LOOPBACK_HOSTS:
            return False
    raise HTTPException(403, "Use HTTPS to sign in to EduScan")


def _cookie_digest(token: str | None) -> str | None:
    if not token or len(token) != 43 or not token.isascii():
        return None
    return hashlib.sha256(token.encode()).hexdigest()


def _session_context(digest: str) -> str:
    # This is a public context identifier. Only the cookie can authenticate a request.
    return hashlib.sha256(f"browser-context:{digest}".encode()).hexdigest()


def require_matching_session_context(request: Request) -> None:
    supplied = request.headers.get(SESSION_CONTEXT_HEADER)
    digest = _cookie_digest(request.cookies.get(SESSION_COOKIE))
    if supplied is not None and (digest is None or supplied != _session_context(digest)):
        raise HTTPException(409, detail={
            "code": "session_changed",
            "message": "The signed-in account changed. Check the active account and try again.",
        })


def issue_session(db: Session, user: User, *, provider: str = "password") -> str:
    now = datetime.utcnow()
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at <= now))
    db.add(AuthSession(
        digest=_cookie_digest(token), user_id=user.id, expires_at=now + SESSION_LIFETIME,
        provider=provider, google_sub=user.google_sub,
        password_stamp=None if provider == "google" else _password_stamp(user),
    ))
    return token


def revoke_session(db: Session, token: str | None) -> None:
    digest = _cookie_digest(token)
    if digest is not None:
        db.execute(delete(AuthSession).where(AuthSession.digest == digest))


def revoke_user_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(SESSION_COOKIE, token, path="/api", max_age=int(SESSION_LIFETIME.total_seconds()),
                        secure=secure, httponly=True, samesite="lax")


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api", secure=secure, httponly=True, samesite="lax")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    digest = _cookie_digest(request.cookies.get(SESSION_COOKIE))
    if digest is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    require_app_request(request)
    secure_session_transport(request)
    require_matching_session_context(request)
    session = db.get(AuthSession, digest)
    if session is None or session.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Session expired. Please sign in again")
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
    if session.provider != "google" and session.password_stamp != _password_stamp(user):
        raise HTTPException(401, "Your password has changed. Please sign in again")
    if session.provider == DEPED_PASSWORD_PROVIDER:
        if not settings.deped_password_recovery or not has_deped_password(user) or session.google_sub != user.google_sub:
            raise HTTPException(status_code=401, detail="Please sign in again")
    elif session.provider == "google" or settings.deped_only or user.google_email:
        if (session.provider != "google" or not user.google_sub
                or session.google_sub != user.google_sub
                or not user.google_email or user.google_email.split("@")[-1] != "deped.gov.ph"):
            raise HTTPException(status_code=401, detail="Please sign in with your DepEd Google account")
    request.state.auth_provider = session.provider
    request.state.session_context = _session_context(digest)
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
