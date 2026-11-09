"""Recover an EduScan password through a previously verified DepEd mailbox."""
from datetime import datetime, timedelta
from email.message import EmailMessage
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import DEPED_PASSWORD_PREFIX, hash_password
from ..config import settings
from ..models import DepedPasswordReset, User
from .audit import add_audit
from .google_login import deped_email


logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=10)
REQUEST_COOLDOWN = timedelta(minutes=1)
MAX_ATTEMPTS = 5


def require_recovery_configuration():
    if not (settings.deped_password_recovery and settings.smtp_host and settings.smtp_from):
        raise HTTPException(503, "Password recovery is unavailable. Contact your school administrator.")


def send_email(recipient: str, subject: str, body: str) -> None:
    try:
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        if settings.smtp_use_ssl:
            connection = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10, context=context)
        else:
            connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with connection as server:
            if not settings.smtp_use_ssl:
                server.starttls(context=context)
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        logger.warning("Password recovery SMTP delivery failed (%s)", type(exc).__name__)


def _verified_user(db: Session, address: str) -> User | None:
    try:
        email = deped_email(address)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return db.scalar(select(User).where(User.google_email == email, User.google_sub != "", User.active.is_(True)))


def _digest(user: User, code: str) -> str:
    message = f"deped-password-reset:{user.id}:{user.google_sub}:{user.google_email}:{user.password_hash}:{code}"
    return hmac.new(settings.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def issue_code(db: Session, address: str) -> tuple[str, str] | None:
    user = _verified_user(db, address)
    if not user:
        return None
    user_id, email = user.id, user.google_email
    now = datetime.utcnow()
    code = f"{secrets.randbelow(100_000_000):08d}"
    values = {"requested_at": now, "code_digest": _digest(user, code), "attempts": 0}
    if db.get(DepedPasswordReset, user_id) is None:
        db.add(DepedPasswordReset(user_id=user_id, **values))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # A concurrent request already created this account's challenge.
            return None
    else:
        replaced = db.execute(update(DepedPasswordReset).where(
            DepedPasswordReset.user_id == user_id,
            DepedPasswordReset.requested_at <= now - REQUEST_COOLDOWN,
        ).values(**values).execution_options(synchronize_session=False))
        db.commit()
        if replaced.rowcount != 1:
            return None
    return email, code


def reset_password(db: Session, address: str, code: str, new_password: str) -> str:
    invalid = HTTPException(400, "The code is invalid or expired. Request a new code and try again.")
    user = _verified_user(db, address)
    challenge = db.get(DepedPasswordReset, user.id) if user else None
    if not challenge or not challenge.code_digest:
        raise invalid

    valid = hmac.compare_digest(challenge.code_digest, _digest(user, code))
    now = datetime.utcnow()
    claimed = db.execute(update(DepedPasswordReset).where(
        DepedPasswordReset.user_id == user.id,
        DepedPasswordReset.requested_at == challenge.requested_at,
        DepedPasswordReset.requested_at > now - CODE_TTL,
        DepedPasswordReset.code_digest == challenge.code_digest,
        DepedPasswordReset.attempts < MAX_ATTEMPTS,
    ).values(
        attempts=DepedPasswordReset.attempts + 1,
        code_digest=None if valid else challenge.code_digest,
    ).execution_options(synchronize_session=False))
    if claimed.rowcount != 1 or not valid:
        db.commit()
        raise invalid

    changed = db.execute(update(User).where(
        User.id == user.id, User.active.is_(True),
        User.google_sub == user.google_sub, User.google_email == user.google_email,
        User.password_hash == user.password_hash,
    ).values(password_hash=DEPED_PASSWORD_PREFIX + hash_password(new_password),
             password_changed_at=now, must_change_password=False, failed_login_count=0,
             locked_until=None).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise invalid
    add_audit(db, user, "PasswordReset", "User", user.id, "EduScan password reset through a verified DepEd mailbox")
    db.commit()
    return user.google_email
