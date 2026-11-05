"""Verify Google identity before provisioning or binding any EduScan account."""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime

import requests
from fastapi import HTTPException
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import User

DOMAIN = "deped.gov.ph"


def deped_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1 or not email.split("@")[0] or email.split("@")[1] != DOMAIN or any(c.isspace() for c in email):
        raise ValueError("Use an email address ending in @deped.gov.ph")
    return email


def _identity(claims: dict) -> tuple[str, str]:
    try:
        email = deped_email(claims.get("email", ""))
    except (ValueError, AttributeError):
        raise HTTPException(403, "Only verified @deped.gov.ph Google accounts can sign in")
    subject = claims.get("sub")
    if claims.get("hd") != DOMAIN or claims.get("email_verified") is not True:
        raise HTTPException(403, "Only verified @deped.gov.ph Google Workspace accounts can sign in")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise HTTPException(401, "Google did not provide a valid account identity")
    return subject, email


class _GoogleRequest(Request):
    def __call__(self, *args, **kwargs):
        kwargs.setdefault("timeout", 10)
        return super().__call__(*args, **kwargs)


def verify_google_credential(credential: str, nonce: str | None = None) -> dict:
    if not settings.google_client_id:
        raise HTTPException(503, "Google sign-in is not configured. Contact your school administrator.")
    try:
        # requests honors the host's certificate configuration; never disable TLS verification.
        with requests.Session() as transport:
            claims = id_token.verify_oauth2_token(credential, _GoogleRequest(session=transport), audience=settings.google_client_id)
    except TransportError:
        raise HTTPException(503, "Google identity verification is temporarily unavailable. Try again.")
    except (ValueError, GoogleAuthError):
        raise HTTPException(401, "Google sign-in could not be verified. Please sign in again.")
    if nonce is not None and (not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce)):
        raise HTTPException(401, "Google sign-in expired. Refresh this page and try again.")
    _identity(claims)
    return claims


def _bind_user(db: Session, claims: dict) -> User:
    subject, email = _identity(claims)
    user = db.scalar(select(User).where(User.google_sub == subject))
    if user is None:
        # Email linking is permitted ONLY for an explicit local administrator reservation.
        user = db.scalar(select(User).where(User.google_email == email))
        if user is not None and user.google_sub is not None:
            raise HTTPException(409, "This DepEd email is linked to another Google identity. Contact your school administrator.")
    if user is not None and not user.active:
        raise HTTPException(403, "Your EduScan account is inactive. Contact your school administrator.")
    if user is None:
        user = User(username=f"google_{secrets.token_hex(16)}", password_hash="!google-only",
                    full_name=(str(claims.get("name") or email).strip() or email)[:160],
                    role="teacher", active=True, must_change_password=False)
        db.add(user)
    user.google_sub = subject
    user.google_email = email
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()
    return user


def google_user(db: Session, claims: dict) -> User:
    try:
        return _bind_user(db, claims)
    except IntegrityError:
        # Another first login may have won the unique identity insert. Re-read once.
        db.rollback()
        try:
            return _bind_user(db, claims)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "This Google identity conflicts with an existing account. Contact your school administrator.")


def reserve_google_email(db: Session, username: str, email: str) -> User:
    """Local setup only: reserve an existing account; Google proves ownership at sign-in."""
    email = deped_email(email)
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    if user is None:
        raise ValueError("Existing EduScan username was not found")
    if not user.active:
        raise ValueError("Cannot link an inactive account")
    if user.google_sub or (user.google_email and user.google_email != email):
        raise ValueError("Account already linked or reserved; refusing to replace its identity")
    owner = db.scalar(select(User).where(User.google_email == email, User.id != user.id))
    if owner:
        raise ValueError("This email already belongs to another EduScan account; reserve identities before first Google login")
    user.google_email = email
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("This email is already reserved for another account")
    return user
