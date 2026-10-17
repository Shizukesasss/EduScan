from __future__ import annotations

import re
import ipaddress
import socket
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Person, SmsOutbox
from .settings_store import get_json, get_secret


DEFAULT_TEMPLATES = {
    "time_in": "EduScan: {name} entered San Jose National High School at {time} on {date}. If unexpected, contact {school_contact}.",
    "time_out": "EduScan: {name} left San Jose National High School at {time} on {date}. If unexpected, contact {school_contact}.",
    "tardiness": "EduScan: {name} arrived at {time} on {date} and was marked late for {class_name} (start: {class_start}). Contact {school_contact} for corrections.",
    "absence": "EduScan: No time-in was recorded for {name} by {absence_cutoff} on {date}; the learner was marked absent pending teacher review. Contact {school_contact}.",
    "enrollment": "EduScan: School enrollment for {name} was {enrollment_action} on {date} at {time}. Contact {school_contact} for questions.",
}


def sms_config(db: Session) -> dict:
    stored = get_json(db, "sms", {})
    templates = {**DEFAULT_TEMPLATES, **stored.get("templates", {})}
    return {
        "enabled": bool(stored.get("enabled", settings.sms_gateway_enabled)),
        "enrollment_notifications": bool(stored.get("enrollment_notifications", True)),
        "dispatch_after": stored.get("dispatch_after"),
        "gateway_url": stored.get("gateway_url", settings.sms_gateway_url),
        "username": stored.get("username", settings.sms_gateway_username),
        "password": get_secret(db, "sms.password", settings.sms_gateway_password),
        "school_contact": stored.get("school_contact", "the school office"),
        "max_messages_per_30_minutes": int(stored.get("max_messages_per_30_minutes", 50)),
        "templates": templates,
    }


def normalize_phone(phone: str) -> str:
    compact = re.sub(r"[^0-9+]", "", phone or "")
    if compact.startswith("09") and len(compact) == 11:
        compact = "+63" + compact[1:]
    elif compact.startswith("639") and len(compact) == 12:
        compact = "+" + compact
    if not re.fullmatch(r"\+?[1-9]\d{7,14}", compact):
        raise HTTPException(status_code=422, detail="Recipient phone number is not a valid international or Philippine mobile number")
    return compact


def validate_local_gateway_url(gateway_url: str) -> tuple[str, int]:
    """Return a validated local host/port and prevent relay requests to public hosts."""
    parsed = urlparse((gateway_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="Gateway URL must be a complete http:// or https:// address")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Put gateway credentials in the username and password fields, not in the URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Gateway URL must be the Local Server base address without /message or a query")

    try:
        resolved = {item[4][0].split("%")[0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail=f"Gateway host could not be resolved on this network: {exc}") from exc
    if not resolved:
        raise HTTPException(status_code=422, detail="Gateway host did not resolve to an address")
    if any(not (ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback or ipaddress.ip_address(address).is_link_local) for address in resolved):
        raise HTTPException(status_code=422, detail="Android Local Server must use a private, loopback, or link-local network address")
    return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def gateway_diagnostics(db: Session) -> dict:
    """Check reachability and the protected docs endpoint without sending SMS."""
    config = sms_config(db)
    result = {
        "enabled": config["enabled"],
        "gateway_url": config["gateway_url"],
        "username_configured": bool(config["username"]),
        "password_configured": bool(config["password"]),
        "reachable": False,
        "ready": False,
        "credentials_accepted": False,
    }
    try:
        host, port = validate_local_gateway_url(config["gateway_url"])
        with socket.create_connection((host, port), timeout=3):
            pass
        result.update({"reachable": True, "host": host, "port": port,
                       "message": "The Android Local Server port is reachable. Send a real test SMS to verify credentials and SIM delivery."})
        if not config["username"] or not config["password"]:
            result["message"] = "The phone is reachable, but the API username or password is missing."
        else:
            response = httpx.get(config["gateway_url"].rstrip("/") + "/docs",
                                 auth=(config["username"], config["password"]), timeout=4)
            if response.status_code in {401, 403}:
                result["message"] = "The phone is reachable, but it rejected the API username or password."
            elif response.status_code == 200:
                result["credentials_accepted"] = True
                result["ready"] = config["enabled"]
                result["message"] = "Phone connection and API credentials checked. Send one test SMS to verify SIM delivery." if config["enabled"] else "Phone connection and API credentials checked, but SMS dispatch is disabled."
            else:
                result["message"] = f"The phone port is reachable, but its protected SMS Gateway docs returned HTTP {response.status_code}. Check the Local Server URL and app version."
    except HTTPException as exc:
        result["message"] = str(exc.detail)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10013:
            result["message"] = "Windows or the current network policy blocked the connection. Check firewall rules and that this laptop may reach the phone's private address."
        else:
            result["message"] = f"The phone did not accept a connection: {exc}"
    except httpx.HTTPError:
        result["message"] = "The phone port is reachable, but its SMS Gateway API did not respond. Check that Local Server is online."
    return result


def render_message(db: Session, event_type: str, person: Person, values: dict) -> str:
    config = sms_config(db)
    template = config["templates"].get(event_type)
    if not template:
        raise HTTPException(status_code=422, detail=f"No SMS template is configured for {event_type}")
    context = {
        "name": person.full_name,
        "studentName": person.full_name,
        "school_contact": config["school_contact"],
        "schoolContact": config["school_contact"],
        **values,
    }
    try:
        return template.format_map(context)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"SMS template uses an unknown field: {exc.args[0]}")


def queue_notice(db: Session, person: Person, event_type: str, values: dict,
                 idempotency_key: str | None = None) -> SmsOutbox | None:
    if person.role != "Student" or not person.guardian_phone:
        return None
    if idempotency_key:
        existing = db.scalar(select(SmsOutbox).where(SmsOutbox.idempotency_key == idempotency_key))
        if existing:
            return existing
    record = SmsOutbox(
        id=str(uuid.uuid4()),
        idempotency_key=idempotency_key,
        person_id=person.id,
        event_type=event_type,
        recipient=normalize_phone(person.guardian_phone),
        message=render_message(db, event_type, person, values),
        status="queued",
    )
    try:
        db.add(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(SmsOutbox).where(SmsOutbox.idempotency_key == idempotency_key))
            if existing:
                return existing
        raise
    db.refresh(record)
    return record


def queue_enrollment_notice(db: Session, person: Person, result: dict) -> dict:
    """Enrollment is already committed; an SMS error must not undo it."""
    if person.role != "Student":
        return {"status": "skipped", "message": "Guardian SMS applies to student enrollments."}
    if not person.guardian_phone:
        return {"status": "skipped", "message": "No SMS queued: this student has no parent/guardian mobile number."}
    try:
        config = sms_config(db)
        if not config["enrollment_notifications"]:
            return {"status": "skipped", "message": "Enrollment SMS notifications are turned off."}
        now = datetime.now(timezone(timedelta(hours=8)))
        record = queue_notice(db, person, "enrollment", {
            "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%I:%M %p"),
            "enrollment_action": "updated" if result.get("action") == "updated" else "completed",
        }, idempotency_key=f"enrollment:{person.id}:{result['model']['version']}")
        ready = bool(config["enabled"] and config["username"] and config["password"])
        message = "Guardian SMS queued for delivery." if ready else "Guardian SMS queued, but delivery is paused until the Android gateway is enabled and configured."
        return {"id": record.id, "status": record.status, "dispatch_ready": ready, "message": message}
    except Exception:
        db.rollback()
        return {"status": "not_queued", "message": "Enrollment saved, but the guardian SMS could not be queued. Check the mobile number and SMS settings."}


def hold_pending_before_activation(db: Session, activated_at: datetime) -> int:
    records = db.scalars(select(SmsOutbox).where(
        SmsOutbox.status.in_(["queued", "failed"]), SmsOutbox.created_at < activated_at,
    )).all()
    for record in records:
        record.status = "held"
        record.next_attempt_at = None
        record.last_error = "Queued before SMS was enabled. Review and requeue explicitly to send."
    return len(records)


def send_record(db: Session, record: SmsOutbox) -> SmsOutbox:
    if record.status not in {"queued", "failed"}:
        return record
    locked = db.scalar(select(SmsOutbox).where(SmsOutbox.id == record.id)
                       .with_for_update().execution_options(populate_existing=True))
    if locked is None:
        return record
    record = locked
    if record.status not in {"queued", "failed"}:
        db.commit()
        return record
    config = sms_config(db)
    now = datetime.utcnow()
    if record.next_attempt_at and record.next_attempt_at > now:
        db.commit()
        return record
    if not config["enabled"]:
        record.status = "queued"
        record.last_error = "Android SMS gateway is not enabled"
        db.commit()
        return record
    cutoff = datetime.fromisoformat(config["dispatch_after"]) if config.get("dispatch_after") else None
    if cutoff and record.created_at < cutoff and (not record.next_attempt_at or record.next_attempt_at < cutoff):
        record.status = "held"
        record.last_error = "Queued before SMS was enabled. Review and requeue explicitly to send."
        db.commit()
        return record
    if not config["username"] or not config["password"]:
        record.status = "queued"
        record.last_error = "Android gateway API username and password are required"
        db.commit()
        return record
    sent_since = now - timedelta(minutes=30)
    recent_sent = db.scalar(select(func.count(SmsOutbox.id)).where(
        SmsOutbox.status.in_(["accepted", "processed", "sent", "delivered"]), SmsOutbox.sent_at >= sent_since,
    )) or 0
    if recent_sent >= config.get("max_messages_per_30_minutes", 50):
        record.status = "queued"
        record.next_attempt_at = now + timedelta(minutes=5)
        record.last_error = "Local 30-minute SMS safety limit reached; delivery was deferred"
        db.commit()
        return record
    record.attempts += 1
    try:
        validate_local_gateway_url(config["gateway_url"])
        url = config["gateway_url"].rstrip("/") + "/message"
        response = httpx.post(
            url,
            auth=(config["username"], config["password"]),
            json={"textMessage": {"text": record.message}, "phoneNumbers": [record.recipient],
                  "withDeliveryReport": True},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        record.gateway_message_id = str(payload.get("id") or payload.get("messageId") or "") or None
        record.status = "accepted"
        record.sent_at = now
        record.next_attempt_at = None
        record.last_error = None
    except Exception as exc:  # Store a concise operational error; never expose the password.
        record.status = "failed"
        record.last_error = str(exc)[:1000]
        delay_minutes = (1, 5, 15)[min(record.attempts - 1, 2)]
        record.next_attempt_at = now + timedelta(minutes=delay_minutes)
        if record.attempts >= 3:
            record.status = "exhausted"
            record.exhausted_at = now
            record.next_attempt_at = None
    db.commit()
    db.refresh(record)
    return record


def dispatch_queued(db: Session, limit: int = 25) -> list[SmsOutbox]:
    records = db.scalars(
        select(SmsOutbox).where(SmsOutbox.status.in_(["queued", "failed"]), SmsOutbox.attempts < 3,
                                or_(SmsOutbox.next_attempt_at.is_(None), SmsOutbox.next_attempt_at <= datetime.utcnow()))
        .order_by(SmsOutbox.created_at).limit(limit)
    ).all()
    return [send_record(db, record) for record in records]


def _gateway_state(config: dict, message_id: str) -> dict | None:
    base = config["gateway_url"].rstrip("/")
    for suffix in (f"/message/{message_id}", f"/messages/{message_id}"):
        try:
            response = httpx.get(base + suffix, auth=(config["username"], config["password"]), timeout=8)
            if response.status_code in {404, 405}:
                continue
            response.raise_for_status()
            return response.json() if response.content else None
        except httpx.HTTPStatusError:
            continue
    return None


def reconcile_record(db: Session, record: SmsOutbox) -> SmsOutbox:
    if not record.gateway_message_id or record.status not in {"accepted", "processed", "sent"}:
        return record
    config = sms_config(db)
    validate_local_gateway_url(config["gateway_url"])
    payload = _gateway_state(config, record.gateway_message_id)
    record.gateway_status_checked_at = datetime.utcnow()
    if payload:
        raw_state = str(payload.get("state") or "")
        recipient_states = [str(item.get("state") or "") for item in payload.get("recipients", []) if isinstance(item, dict)]
        if recipient_states:
            raw_state = "Delivered" if any(item == "Delivered" for item in recipient_states) else "Failed" if any(item == "Failed" for item in recipient_states) else raw_state
        mapped = {"Pending": "accepted", "Processed": "processed", "Sent": "sent", "Delivered": "delivered",
                  "Failed": "failed", "Cancelled": "cancelled", "Cancelling": "accepted"}.get(raw_state)
        if mapped:
            record.status = mapped
            if mapped == "delivered":
                record.delivered_at = datetime.utcnow()
            elif mapped == "cancelled":
                record.cancelled_at = datetime.utcnow()
            elif mapped == "failed":
                record.last_error = str(payload.get("reason") or "Android gateway reported a terminal failure")[:1000]
    db.commit()
    db.refresh(record)
    return record


def reconcile_outbox(db: Session, limit: int = 100) -> list[SmsOutbox]:
    items = db.scalars(select(SmsOutbox).where(
        SmsOutbox.gateway_message_id.is_not(None), SmsOutbox.status.in_(["accepted", "processed", "sent"]),
    ).order_by(SmsOutbox.created_at).limit(limit)).all()
    results = []
    for item in items:
        try:
            results.append(reconcile_record(db, item))
        except Exception:
            item.gateway_status_checked_at = datetime.utcnow()
            db.commit()
            results.append(item)
    return results


def requeue_record(db: Session, record: SmsOutbox) -> SmsOutbox:
    if record.status not in {"failed", "exhausted", "cancelled", "held"}:
        raise HTTPException(status_code=409, detail="Only failed, exhausted, cancelled, or held messages can be requeued")
    record.status = "queued"
    record.attempts = 0
    record.gateway_message_id = None
    record.last_error = None
    record.next_attempt_at = datetime.utcnow()
    record.sent_at = None
    record.delivered_at = None
    record.cancelled_at = None
    record.exhausted_at = None
    db.commit()
    db.refresh(record)
    return record


def cancel_record(db: Session, record: SmsOutbox) -> SmsOutbox:
    if record.status in {"delivered", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"A {record.status} message cannot be cancelled")
    if record.gateway_message_id and record.status in {"accepted", "processed"}:
        config = sms_config(db)
        base = config["gateway_url"].rstrip("/")
        cancelled_remotely = False
        for suffix in (f"/message/{record.gateway_message_id}", f"/messages/{record.gateway_message_id}"):
            response = httpx.delete(base + suffix, auth=(config["username"], config["password"]), timeout=8)
            if response.status_code in {200, 202, 204}:
                cancelled_remotely = True
                break
            if response.status_code not in {404, 405}:
                raise HTTPException(status_code=409, detail="The Android gateway could not cancel this message; reconcile its status first")
        if not cancelled_remotely:
            raise HTTPException(status_code=409, detail="This Local Server version does not expose remote cancellation for an accepted message")
    record.status = "cancelled"
    record.cancelled_at = datetime.utcnow()
    record.next_attempt_at = None
    db.commit()
    db.refresh(record)
    return record


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}••••{phone[-3:]}" if len(phone) > 7 else "••••"


def dispatch_record_by_id(record_id: str) -> None:
    from ..database import SessionLocal
    with SessionLocal() as db:
        record = db.get(SmsOutbox, record_id)
        if record and record.status in {"queued", "failed"} and record.attempts < 3:
            send_record(db, record)


def dispatch_outbox() -> None:
    from ..database import SessionLocal
    with SessionLocal() as db:
        dispatch_queued(db)
        reconcile_outbox(db)
