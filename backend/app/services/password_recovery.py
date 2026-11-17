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

from ..auth import DEPED_PASSWORD_PREFIX, hash_password, revoke_user_sessions, verify_password
from ..config import settings
from ..models import DepedPasswordReset, RecoveryEmailVerification, User
from .audit import add_audit
from .google_login import DOMAIN, deped_email


logger = logging.getLogger(__name__)
CODE_TTL = timedelta(minutes=10)
REQUEST_COOLDOWN = timedelta(minutes=1)
MAX_ATTEMPTS = 5


def admin_recovery_enabled() -> bool:
    return bool(not settings.deped_only and settings.smtp_host and settings.smtp_from)


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
    if not admin_recovery_enabled() or (settings.deped_password_recovery and username.endswith(f"@{DOMAIN}")):
        return None
    return db.scalar(select(User).where(func.lower(User.username) == username,
                                        User.role == "admin", User.active.is_(True),
                                        User.google_email.is_(None), User.google_sub.is_(None)))


def _admin_email(user: User) -> str | None:
    if user.recovery_email:
        return user.recovery_email
    if user.username.lower() == settings.admin_recovery_username:
        return settings.admin_recovery_email or None
    return None


def _sign(message: str) -> str:
    return hmac.new(settings.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def _digest(user: User, code: str, *, admin: bool, email: str) -> str:
    if admin:
        message = f"admin-password-reset:{user.id}:{user.username}:{email}:{user.password_hash}:{code}"
    else:
        message = f"deped-password-reset:{user.id}:{user.google_sub}:{email}:{user.password_hash}:{code}"
    return _sign(message)


def _store_challenge(db: Session, model, user_id: int, digest: str, **fields) -> bool:
    now = datetime.utcnow()
    values = dict(requested_at=now, code_digest=digest, attempts=0, **fields)
    if db.get(model, user_id) is None:
        db.add(model(user_id=user_id, **values))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # A concurrent request already created this account's challenge.
            return False
        return True
    replaced = db.execute(update(model).where(
        model.user_id == user_id, model.requested_at <= now - REQUEST_COOLDOWN,
    ).values(**values).execution_options(synchronize_session=False))
    db.commit()
    return replaced.rowcount == 1


def issue_code(db: Session, identifier: str, *, admin: bool = False) -> tuple[str, str] | None:
    user = _admin_user(db, identifier) if admin else _verified_user(db, identifier)
    if not user:
        return None
    email = _admin_email(user) if admin else user.google_email
    if not email:
        return None
    code = f"{secrets.randbelow(100_000_000):08d}"
    if _store_challenge(db, DepedPasswordReset, user.id, _digest(user, code, admin=admin, email=email)):
        return email, code
    return None


def _invalid_code() -> HTTPException:
    return HTTPException(400, "The code is invalid or expired. Request a new code and try again.")


def _claim_challenge(db: Session, challenge, digest: str, now: datetime) -> None:
    if not challenge.code_digest:
        raise _invalid_code()
    valid = hmac.compare_digest(challenge.code_digest, digest)
    model = type(challenge)
    claimed = db.execute(update(model).where(
        model.user_id == challenge.user_id,
        model.requested_at == challenge.requested_at,
        model.requested_at > now - CODE_TTL,
        model.code_digest == challenge.code_digest,
        model.attempts < MAX_ATTEMPTS,
    ).values(
        attempts=model.attempts + 1,
        code_digest=None if valid else challenge.code_digest,
    ).execution_options(synchronize_session=False))
    if claimed.rowcount != 1 or not valid:
        db.commit()
        raise _invalid_code()


def reset_password(db: Session, identifier: str, code: str, new_password: str, *, admin: bool = False) -> str:
    user = _admin_user(db, identifier) if admin else _verified_user(db, identifier)
    if not user:
        raise _invalid_code()
    email = _admin_email(user) if admin else user.google_email
    challenge = db.get(DepedPasswordReset, user.id)
    if not email or not challenge:
        raise _invalid_code()
    now = datetime.utcnow()
    _claim_challenge(db, challenge, _digest(user, code, admin=admin, email=email), now)

    account = update(User).where(
        User.id == user.id, User.active.is_(True),
        User.google_sub == user.google_sub, User.google_email == user.google_email,
        User.password_hash == user.password_hash,
    )
    if admin:
        account = account.where(User.role == "admin", User.username == user.username,
                                User.recovery_email == user.recovery_email)
    prefix = "" if admin else DEPED_PASSWORD_PREFIX
    changed = db.execute(account.values(password_hash=prefix + hash_password(new_password),
             password_changed_at=now, must_change_password=False, failed_login_count=0,
             locked_until=None).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise _invalid_code()
    revoke_user_sessions(db, user.id)
    mailbox = "the administrator recovery mailbox" if admin else "a verified DepEd mailbox"
    add_audit(db, user, "PasswordReset", "User", user.id, f"EduScan password reset through {mailbox}")
    db.commit()
    return email


def require_local_admin(user: User) -> None:
    if user.google_sub is not None or user.google_email is not None:
        raise HTTPException(403, "This account uses DepEd Google sign-in.")


def _email_verification_digest(user: User, email: str, code: str) -> str:
    return _sign(f"admin-recovery-email:{user.id}:{user.username}:{email}:{user.password_hash}:{code}")


def issue_email_verification(db: Session, user: User, email: str, password: str) -> str:
    require_local_admin(user)
    require_recovery_configuration(admin=True)
    if not verify_password(password, user.password_hash):
        raise HTTPException(422, "That password is incorrect. Check it and try again.")
    code = f"{secrets.randbelow(100_000_000):08d}"
    if not _store_challenge(db, RecoveryEmailVerification, user.id,
                            _email_verification_digest(user, email, code), email=email):
        raise HTTPException(429, "Wait a minute before requesting another verification code.")
    return code


def verify_recovery_email(db: Session, user: User, code: str) -> str:
    require_local_admin(user)
    require_recovery_configuration(admin=True)
    challenge = db.get(RecoveryEmailVerification, user.id)
    if not challenge:
        raise _invalid_code()
    email = challenge.email
    _claim_challenge(db, challenge, _email_verification_digest(user, email, code), datetime.utcnow())
    changed = db.execute(update(User).where(
        User.id == user.id, User.username == user.username, User.role == "admin", User.active.is_(True),
        User.google_sub.is_(None), User.google_email.is_(None), User.password_hash == user.password_hash,
        User.recovery_email == user.recovery_email,
    ).values(recovery_email=email).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Your account changed. Sign in again before verifying a recovery email.")
    add_audit(db, user, "RecoveryEmailVerified", "User", user.id, "Administrator verified a recovery email")
    db.commit()
    return email
