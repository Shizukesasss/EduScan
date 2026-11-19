"""Build a small, role-scoped inbox from existing workflow records."""

from datetime import datetime, timedelta

from sqlalchemy import case, delete, func, or_, select

from ..models import BackupRun, GeneratedReport, RecognitionReview, SmsOutbox, StationSyncOperation, SystemAuditEvent, SystemSetting
from ..models_grading import Gradebook
from . import station_sync
from .grading import teacher_gradebook_scope
from .settings_store import upsert_value


def _alert(key, timestamp, title, description, link):
    return {"id": key, "created_at": timestamp.isoformat(timespec="microseconds") + "Z",
            "title": title, "description": description, "href": link}


def _queue_alert(db, entries, time_column, id_column, category, title, description, link):
    entry = db.execute(entries.order_by(time_column.desc(), id_column.desc()).limit(1)).first()
    if entry is None:
        return []
    item_id, timestamp, total = entry
    return [_alert(f"{category}-{item_id}", timestamp, title, description.format(total=total), link.format(id=item_id))]


def _teacher_alerts(db, user, since, report_scope):
    reports = db.execute(select(GeneratedReport.id, GeneratedReport.created_at, GeneratedReport.report_type).where(
        GeneratedReport.created_at >= since, report_scope,
    ).order_by(GeneratedReport.created_at.desc(), GeneratedReport.id.desc()).limit(20))
    alerts = []
    for report in reports:
        sf2 = report.report_type == "Official SF2"
        destination = "/teacher/reports#released-sf2" if sf2 else "/teacher/reports#learner-reports"
        alerts.append(_alert(
            f"report-{report.id}", report.created_at, f"{report.report_type} available",
            "A report for one of your assigned classes is ready to review.", destination,
        ))

    reviewed_at = case((Gradebook.status == "Draft", Gradebook.reopened_at), else_=Gradebook.finalized_at)
    gradebooks = db.execute(select(
        Gradebook.id, Gradebook.status, Gradebook.subject_name, Gradebook.section_name, reviewed_at.label("reviewed_at"),
    ).where(
        Gradebook.teacher_user_id == user.id, teacher_gradebook_scope(user.id),
        Gradebook.status.in_(("Finalized", "Locked", "Draft")), reviewed_at >= since,
    ).order_by(reviewed_at.desc(), Gradebook.id.desc()).limit(20))
    for book in gradebooks:
        outcome = "reopened" if book.status == "Draft" else "finalized"
        alerts.append(_alert(
            f"gradebook-{book.id}-{outcome}-{book.reviewed_at.strftime('%Y%m%d%H%M%S%f')}", book.reviewed_at,
            f"Gradebook {outcome}", f"{book.subject_name} · {book.section_name}.", "/teacher/grading",
        ))
    return alerts


def candidates(db, user, *, report_scope=None):
    since = datetime.utcnow() - timedelta(days=30)
    if user.role == "teacher":
        return _teacher_alerts(db, user, since, report_scope)

    alerts = []
    if user.role in {"admin", "records_officer", "privacy_officer"}:
        review = select(RecognitionReview.id, RecognitionReview.created_at, func.count().over()).where(
            RecognitionReview.status == "Open", RecognitionReview.created_at >= since,
        )
        alerts.extend(_queue_alert(db, review, RecognitionReview.created_at, RecognitionReview.id, "recognition",
                                   "Gate recognition needs review", "{total} open recognition reviews.",
                                   "/dashboard/attendance#recognition-reviews"))
    if user.role in {"admin", "records_officer"}:
        failed_at = func.coalesce(SmsOutbox.exhausted_at, SmsOutbox.sent_at, SmsOutbox.created_at)
        failed_sms = select(SmsOutbox.id, failed_at, func.count().over()).where(
            SmsOutbox.status.in_(("failed", "exhausted")), failed_at >= since,
        )
        alerts.extend(_queue_alert(db, failed_sms, failed_at, SmsOutbox.id, "sms",
                                   "Guardian SMS delivery failed", "{total} recent messages need attention.",
                                   "/dashboard/setup?tab=sms&message={id}#sms-delivery"))
    if user.role == "records_officer":
        submitted = select(Gradebook.id, Gradebook.submitted_at, func.count().over()).where(
            Gradebook.status == "Submitted", Gradebook.submitted_at >= since, Gradebook.is_legacy_readonly.is_(False),
        )
        alerts.extend(_queue_alert(db, submitted, Gradebook.submitted_at, Gradebook.id, "grading",
                                   "Gradebooks ready for review", "{total} recently submitted gradebooks.",
                                   "/dashboard/grading"))
    if user.role == "school_head":
        finalized = select(Gradebook.id, Gradebook.finalized_at, func.count().over()).where(
            Gradebook.status.in_(("Finalized", "Locked")), Gradebook.finalized_at >= since,
            Gradebook.is_legacy_readonly.is_(False),
        )
        alerts.extend(_queue_alert(db, finalized, Gradebook.finalized_at, Gradebook.id, "grading",
                                   "Finalized gradebooks available", "{total} recently finalized gradebooks.",
                                   "/dashboard/grading"))
    if user.role in {"admin", "ict"}:
        backup = db.execute(select(BackupRun.id, BackupRun.created_at, BackupRun.status).where(
            BackupRun.created_at >= since, BackupRun.status.in_(("Completed", "Failed")),
        ).order_by(BackupRun.created_at.desc(), BackupRun.id.desc()).limit(1)).first()
        if backup and backup.status == "Failed":
            alerts.append(_alert(f"backup-{backup.id}", backup.created_at, "Latest backup failed",
                                 "Review the failure in Backup & recovery.", "/dashboard/administration?tab=backup"))
    if user.role == "admin":
        lockouts = select(SystemAuditEvent.id, SystemAuditEvent.created_at, func.count().over()).where(
            SystemAuditEvent.entity_type == "User", SystemAuditEvent.action == "Lockout",
            SystemAuditEvent.created_at >= since,
        )
        alerts.extend(_queue_alert(db, lockouts, SystemAuditEvent.created_at, SystemAuditEvent.id, "lockout",
                                   "Account lockout recorded", "{total} recent automatic account lockouts.",
                                   "/dashboard/administration?tab=activity"))
    if user.role == "admin" and station_sync.enabled:
        conflicts = select(StationSyncOperation.id, StationSyncOperation.created_at, func.count().over()).where(
            StationSyncOperation.status == "conflict", StationSyncOperation.created_at >= since,
        )
        alerts.extend(_queue_alert(db, conflicts, StationSyncOperation.created_at, StationSyncOperation.id, "sync",
                                   "Offline sync needs review", "{total} queued operations need review.",
                                   "/dashboard/setup?tab=gate-network"))
    return alerts


def _prefix(user_id):
    return f"notifications:{user_id}:"


def inbox(db, user, report_scope=None):
    alerts = candidates(db, user, report_scope=report_scope)
    prefix = _prefix(user.id)
    states = dict(db.execute(select(SystemSetting.key, SystemSetting.value).where(
        SystemSetting.key.in_([prefix + alert["id"] for alert in alerts]),
    )).all()) if alerts else {}
    rows = []
    for alert in sorted(alerts, key=lambda item: (item["created_at"], item["id"]), reverse=True):
        state = states.get(prefix + alert["id"])
        if state != "deleted":
            rows.append({**alert, "read": state == "read"})
    return {"items": rows, "unread": sum(not row["read"] for row in rows)}


def save_state(db, user_id, alert_id, state):
    now = datetime.utcnow()
    prefix = _prefix(user_id)
    upsert_value(db, prefix + alert_id, state, now, preserve="deleted")
    db.execute(delete(SystemSetting).where(
        SystemSetting.key.startswith(prefix), SystemSetting.updated_at < now - timedelta(days=60),
    ))
    db.commit()
