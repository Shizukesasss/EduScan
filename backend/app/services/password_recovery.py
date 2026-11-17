"""Recover EduScan passwords through a verified or operator-configured mailbox."""
from datetime import datetime, timedelta
from email.message import EmailMessage
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import DEPED_PASSWORD_PREFIX, hash_password, revoke_user_sessions
from ..config import settings
from ..models import DepedPasswordReset, User
from .audit import add_audit
from .google_login import DOMAIN, deped_email


logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=10)
REQUEST_COOLDOWN = timedelta(minutes=1)
MAX_ATTEMPTS = 5


def admin_recovery_enabled() -> bool:
    username = settings.admin_recovery_username
    return bool(not settings.deped_only and username and settings.admin_recovery_email
                and settings.smtp_host and settings.smtp_from
                and not (settings.deped_password_recovery and username.endswith(f"@{DOMAIN}")))


def require_recovery_configuration(*, admin: bool = False):
    enabled = admin_recovery_enabled() if admin else (
        settings.deped_password_recovery and settings.smtp_host and settings.smtp_from)
    if not enabled:
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


def _admin_user(db: Session, username: str) -> User | None:
    username = username.strip().lower()
    if not admin_recovery_enabled() or username != settings.admin_recovery_username:
        return None
    return db.scalar(select(User).where(func.lower(User.username) == username,
                                        User.role == "admin", User.active.is_(True),
                                        User.google_email.is_(None), User.google_sub.is_(None)))


def _digest(user: User, code: str, *, admin: bool) -> str:
    if admin:
        message = f"admin-password-reset:{user.id}:{user.username}:{settings.admin_recovery_email}:{user.password_hash}:{code}"
    else:
        message = f"deped-password-reset:{user.id}:{user.google_sub}:{user.google_email}:{user.password_hash}:{code}"
    return hmac.new(settings.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def issue_code(db: Session, identifier: str, *, admin: bool = False) -> tuple[str, str] | None:
    user = _admin_user(db, identifier) if admin else _verified_user(db, identifier)
    if not user:
        return None
    user_id = user.id
    email = settings.admin_recovery_email if admin else user.google_email
    now = datetime.utcnow()
    code = f"{secrets.randbelow(100_000_000):08d}"
    values = {"requested_at": now, "code_digest": _digest(user, code, admin=admin), "attempts": 0}
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


def reset_password(db: Session, identifier: str, code: str, new_password: str, *, admin: bool = False) -> str:
    invalid = HTTPException(400, "The code is invalid or expired. Request a new code and try again.")
    user = _admin_user(db, identifier) if admin else _verified_user(db, identifier)
    challenge = db.get(DepedPasswordReset, user.id) if user else None
    if not challenge or not challenge.code_digest:
        raise invalid

    valid = hmac.compare_digest(challenge.code_digest, _digest(user, code, admin=admin))
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

    account = update(User).where(
        User.id == user.id, User.active.is_(True),
        User.google_sub == user.google_sub, User.google_email == user.google_email,
        User.password_hash == user.password_hash,
    )
    if admin:
        account = account.where(User.role == "admin", User.username == user.username)
    prefix = "" if admin else DEPED_PASSWORD_PREFIX
    changed = db.execute(account.values(password_hash=prefix + hash_password(new_password),
             password_changed_at=now, must_change_password=False, failed_login_count=0,
             locked_until=None).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise invalid
    revoke_user_sessions(db, user.id)
    mailbox = "the configured administrator mailbox" if admin else "a verified DepEd mailbox"
    add_audit(db, user, "PasswordReset", "User", user.id, f"EduScan password reset through {mailbox}")
    db.commit()
    return settings.admin_recovery_email if admin else user.google_email
