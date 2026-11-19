"""Manage local password sign-in addresses and one-time approvals."""

import hashlib
import json
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import String, cast, delete, func, literal, or_, select, update
from sqlalchemy.exc import IntegrityError

from ..auth import hash_password, revoke_user_sessions, verify_password
from ..config import settings
from ..models import SystemSetting, User
from .audit import add_audit
from .google_login import DOMAIN
from .settings_store import upsert_value


REQUEST_PREFIX = "account.login.email_request."


def _login_key(user_id):
    return f"account.login.email.{user_id}"


def _address_key(email):
    return "account.login.address." + hashlib.sha256(email.encode()).hexdigest()


def login_email(db, user):
    return user.google_email or db.scalar(select(SystemSetting.value).where(SystemSetting.key == _login_key(user.id))) or ""


def mapped_account(db, identifier):
    owner = db.scalar(select(SystemSetting.value).where(SystemSetting.key == _address_key(identifier))) if "@" in identifier else None
    return db.get(User, int(owner)) if owner is not None else None


def password_account(db, identifier):
    mapped = mapped_account(db, identifier)
    if mapped:
        return mapped
    user = db.scalar(select(User).where(func.lower(User.username) == identifier))
    if user and not user.google_email and login_email(db, user):
        return None
    return user


def _require_local_account(user):
    if settings.deped_only or user.google_email:
        raise HTTPException(403, "Manage your sign-in email and password through your Google account.")


def _check_address(db, user, email):
    address = email.lower()
    if address.endswith("@" + DOMAIN):
        raise HTTPException(422, "Use an email address outside the DepEd Google sign-in domain.")
    if address == login_email(db, user):
        raise HTTPException(422, "Enter a different email address.")
    if db.get(SystemSetting, _address_key(address)) or db.scalar(select(User.id).where(
        User.id != user.id, or_(func.lower(User.username) == address, func.lower(User.google_email) == address),
    )):
        raise HTTPException(409, "That email address is already in use.")
    return address


def _request_row(db, user_id):
    return db.get(SystemSetting, REQUEST_PREFIX + str(user_id))


def request_status(db, user):
    row = _request_row(db, user.id)
    return json.loads(row.value) if row else None


def submit_request(db, user, email):
    _require_local_account(user)
    address = _check_address(db, user, email)
    previous = request_status(db, user)
    if previous and previous["email"] == address and previous["status"] in {"pending", "approved"}:
        return previous
    now = datetime.utcnow()
    requested = {"id": uuid.uuid4().hex, "email": address, "status": "pending", "created_at": now.isoformat() + "Z"}
    upsert_value(db, REQUEST_PREFIX + str(user.id), json.dumps(requested), now)
    add_audit(db, user, "Request", "AccountEmail", user.id, "User requested a sign-in email change")
    db.commit()
    return requested


def pending_requests(db):
    rows = db.execute(select(User.id, User.full_name, User.username, SystemSetting.value)
                      .select_from(SystemSetting).join(
                          User, SystemSetting.key == literal(REQUEST_PREFIX) + cast(User.id, String),
                      ).where(User.active.is_(True), User.google_email.is_(None))
                      .order_by(SystemSetting.updated_at.desc()))
    items = []
    for row in rows:
        request = json.loads(row.value)
        if request["status"] == "pending":
            items.append({"user_id": row.id, "full_name": row.full_name, "username": row.username, **request})
    return items


def review_request(db, administrator, user_id, request_id, approve):
    target = db.get(User, user_id)
    row = _request_row(db, user_id)
    if not target or not target.active or not row:
        raise HTTPException(404, "That email change request is unavailable.")
    _require_local_account(target)
    request = json.loads(row.value)
    if request["id"] != request_id or request["status"] != "pending":
        raise HTTPException(409, "That request changed. Refresh the approvals list.")
    if approve:
        _check_address(db, target, request["email"])
    request["status"] = "approved" if approve else "declined"
    result = db.execute(update(SystemSetting).where(SystemSetting.key == row.key, SystemSetting.value == row.value)
                        .values(value=json.dumps(request), updated_at=datetime.utcnow()))
    if result.rowcount != 1:
        raise HTTPException(409, "That request changed. Refresh the approvals list.")
    add_audit(db, administrator, "Approve" if approve else "Decline", "AccountEmail", user_id,
              "Administrator reviewed a sign-in email change request")
    db.commit()
    return request


def change_credentials(db, user, payload):
    _require_local_account(user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(422, "That current password is incorrect.")
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "Choose a password different from your current password.")
    address = _check_address(db, user, payload.email)
    approval_row = _request_row(db, user.id)
    if user.role != "admin":
        approval = json.loads(approval_row.value) if approval_row else None
        if not approval or approval["email"] != address or approval["status"] != "approved":
            raise HTTPException(403, "An administrator must approve this exact email address first.")
    old_address = login_email(db, user)
    now = datetime.utcnow()
    changed = db.execute(update(User).where(
        User.id == user.id, User.active.is_(True), User.password_hash == user.password_hash, User.google_email.is_(None),
        User.role == user.role,
    ).values(password_hash=hash_password(payload.new_password), password_changed_at=now, failed_login_count=0,
             locked_until=None))
    if changed.rowcount != 1:
        raise HTTPException(409, "Your account changed. Sign in again and retry.")
    if approval_row:
        consumed = db.execute(delete(SystemSetting).where(SystemSetting.key == approval_row.key,
                                                          SystemSetting.value == approval_row.value))
        if consumed.rowcount != 1:
            raise HTTPException(409, "The approval changed. Reload your profile and try again.")
    if old_address:
        db.execute(delete(SystemSetting).where(SystemSetting.key == _address_key(old_address),
                                               SystemSetting.value == str(user.id)))
    db.add(SystemSetting(key=_address_key(address), value=str(user.id), updated_at=now))
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "That email address is already in use.") from exc
    upsert_value(db, _login_key(user.id), address, now)
    revoke_user_sessions(db, user.id)
    add_audit(db, user, "CredentialChange", "User", user.id, "Account owner changed their sign-in email and password")
    db.commit()
