from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AttendanceCorrection, AttendanceEvent, AttendanceResetAudit, CalendarException, ClassSchedule, ExcusedAbsence, Person, PersonnelSchedule, User
from .settings_store import get_json
from .sms import queue_notice


MANILA = timezone(timedelta(hours=8), "Asia/Manila")


def local_now() -> datetime:
    return datetime.now(MANILA)


def attendance_config(db: Session) -> dict:
    return {"absence_cutoff": "09:00", "duplicate_cooldown_seconds": 45, "auto_close_enabled": True,
            **get_json(db, "attendance", {})}


def calendar_exception(db: Session, day: date) -> CalendarException | None:
    return db.scalar(select(CalendarException).where(CalendarException.event_date == day))


def is_instructional_day(db: Session, day: date) -> bool:
    if day.weekday() >= 5:
        return False
    exception = calendar_exception(db, day)
    return not exception or exception.event_type == "Special Schedule"


def effective_absence_cutoff(db: Session, day: date) -> time:
    exception = calendar_exception(db, day)
    if exception and exception.event_type == "Special Schedule" and exception.absence_cutoff:
        return exception.absence_cutoff
    return time.fromisoformat(attendance_config(db)["absence_cutoff"])


def person_absence_cutoff(db: Session, person: Person, day: date) -> time:
    exception = calendar_exception(db, day)
    if exception and exception.event_type == "Special Schedule" and exception.absence_cutoff:
        return exception.absence_cutoff
    schedule = applicable_schedule(db, person, day)
    if schedule and schedule.absence_cutoff:
        return schedule.absence_cutoff
    return effective_absence_cutoff(db, day)


def applicable_schedule(db: Session, person: Person, day: date) -> ClassSchedule | PersonnelSchedule | None:
    if person.role == "Student":
        if not person.grade or not person.section:
            return None
        schedules = db.scalars(
            select(ClassSchedule).where(
                ClassSchedule.grade == person.grade,
                ClassSchedule.section == person.section,
                ClassSchedule.active.is_(True),
            ).order_by(ClassSchedule.start_time)
        ).all()
        return next((item for item in schedules if str(day.weekday()) in item.weekdays.split(",")), None)
    if person.role not in {"Faculty", "Non-teaching Personnel"}:
        return None
    schedules = db.scalars(select(PersonnelSchedule).where(
        PersonnelSchedule.role == person.role, PersonnelSchedule.active.is_(True),
    ).order_by(PersonnelSchedule.start_time)).all()
    eligible = [item for item in schedules if str(day.weekday()) in item.weekdays.split(",")]
    general = eligible
    return (general or [None])[0]


def latest_day_reset(db: Session, day: date) -> AttendanceResetAudit | None:
    return db.scalar(
        select(AttendanceResetAudit).where(AttendanceResetAudit.attendance_date == day)
        .order_by(AttendanceResetAudit.created_at.desc())
    )


def raw_row(db: Session, person: Person, day: date) -> dict:
    reset = latest_day_reset(db, day)
    event_query = select(AttendanceEvent).where(AttendanceEvent.person_id == person.id, AttendanceEvent.event_date == day)
    if reset:
        event_query = event_query.where(AttendanceEvent.created_at > reset.created_at)
    events = db.scalars(event_query.order_by(AttendanceEvent.event_time, AttendanceEvent.created_at)).all()
    time_in_event = next((event for event in events if event.direction == "Time In"), None)
    time_out_event = next((event for event in reversed(events) if event.direction == "Time Out"), None)
    absence_event = next((event for event in events if event.status == "Absent"), None)
    exception = calendar_exception(db, day)
    excused = db.scalar(select(ExcusedAbsence).where(
        ExcusedAbsence.person_id == person.id, ExcusedAbsence.event_date == day,
    ))
    status = "No scan"
    source = f"Clean slate started by {reset.actor_name}" if reset else "—"
    if person.enrollment_start_date and day < person.enrollment_start_date:
        status, source = "Not Enrolled", f"Enrollment starts {person.enrollment_start_date.isoformat()}"
    elif person.enrollment_end_date and day > person.enrollment_end_date:
        status, source = "Transferred Out", f"Enrollment ended {person.enrollment_end_date.isoformat()}"
    elif time_in_event:
        last_gate_event = next((event for event in reversed(events) if event.direction in {"Time In", "Time Out"}), time_in_event)
        status = "Time Out" if last_gate_event.direction == "Time Out" else time_in_event.status
        source = last_gate_event.source
    elif excused:
        status, source = "Excused", f"Excused by {excused.actor_name}"
    elif exception and exception.event_type in {"Holiday", "Suspended"}:
        status, source = exception.event_type, exception.reason
    elif day.weekday() >= 5:
        status, source = "Weekend", "Non-instructional day"
    elif absence_event:
        status, source = "Absent", absence_event.source
    correction_query = select(AttendanceCorrection).where(
        AttendanceCorrection.person_id == person.id,
        AttendanceCorrection.attendance_date == day,
    )
    if reset:
        correction_query = correction_query.where(AttendanceCorrection.created_at > reset.created_at)
    correction = db.scalar(correction_query.order_by(AttendanceCorrection.created_at.desc()))
    row = {
        "person_id": person.id,
        "external_id": person.external_id,
        "lrn": person.lrn,
        "full_name": person.full_name,
        "sex": person.sex,
        "role": person.role,
        "grade": person.grade,
        "section": person.section,
        "enrollment_status": person.enrollment_status,
        "enrollment_start_date": person.enrollment_start_date,
        "enrollment_end_date": person.enrollment_end_date,
        "transfer_school": person.transfer_school,
        "time_in": time_in_event.event_time if time_in_event else None,
        "time_out": time_out_event.event_time if time_out_event else None,
        "status": status,
        "source": source,
        "correction_reason": None,
    }
    if correction:
        row.update(time_in=correction.time_in, time_out=correction.time_out, status=correction.status,
                   source=f"Corrected by {correction.actor_name}", correction_reason=correction.reason)
    return row


def _identity_key(person: Person) -> str:
    identifier = person.lrn if person.role == "Student" and person.lrn else person.external_id
    return f"{person.role.casefold()}:{identifier.strip().casefold()}"


def active_people(db: Session, grade: str | None = None, section: str | None = None,
                  students_only: bool = False) -> list[Person]:
    query = select(Person).where(Person.active.is_(True))
    if students_only:
        query = query.where(Person.role == "Student")
    if grade:
        query = query.where(Person.grade == grade)
    if section:
        query = query.where(Person.section == section)
    people = db.scalars(query.order_by(Person.role, Person.grade, Person.section, Person.full_name, Person.external_id)).all()
    unique: list[Person] = []
    seen: set[str] = set()
    for person in people:
        key = _identity_key(person)
        if key in seen:
            continue
        seen.add(key)
        unique.append(person)
    return unique


def list_rows(db: Session, day: date, grade: str | None = None, section: str | None = None,
              students_only: bool = False) -> list[dict]:
    return [raw_row(db, person, day) for person in active_people(db, grade, section, students_only)]


def record_gate_match(db: Session, person: Person, distance: float, now: datetime | None = None) -> dict:
    now = now or local_now()
    day, clock = now.date(), now.timetz().replace(tzinfo=None)
    config = attendance_config(db)
    reset = latest_day_reset(db, day)
    recent_query = select(AttendanceEvent).where(
        AttendanceEvent.person_id == person.id,
        AttendanceEvent.event_date == day,
        AttendanceEvent.direction.in_(["Time In", "Time Out"]),
    )
    if reset:
        recent_query = recent_query.where(AttendanceEvent.created_at > reset.created_at)
    recent = db.scalar(recent_query.order_by(AttendanceEvent.created_at.desc()))
    utc_now = datetime.utcnow()
    if recent and (utc_now - recent.created_at).total_seconds() < int(config["duplicate_cooldown_seconds"]):
        remaining = int(config["duplicate_cooldown_seconds"] - (utc_now - recent.created_at).total_seconds())
        return {"recorded": False, "message": f"Duplicate scan ignored; try again in {max(1, remaining)} seconds"}
    day_events_query = select(AttendanceEvent).where(
        AttendanceEvent.person_id == person.id,
        AttendanceEvent.event_date == day,
        AttendanceEvent.direction.in_(["Time In", "Time Out"]),
    )
    if reset:
        day_events_query = day_events_query.where(AttendanceEvent.created_at > reset.created_at)
    day_events = db.scalars(day_events_query.order_by(AttendanceEvent.created_at, AttendanceEvent.event_time)).all()
    last_direction = day_events[-1].direction if day_events else None
    direction = "Time Out" if last_direction == "Time In" else "Time In"
    first_arrival = direction == "Time In" and not any(item.direction == "Time In" for item in day_events)
    schedule = applicable_schedule(db, person, day) if first_arrival else None
    status = "Present" if direction == "Time In" else "Time Out"
    event_type = "time_in" if direction == "Time In" else "time_out"
    day_exception = calendar_exception(db, day)
    schedule_start = day_exception.start_time if day_exception and day_exception.event_type == "Special Schedule" and day_exception.start_time else (schedule.start_time if schedule else None)
    if first_arrival and schedule_start:
        grace = schedule.late_grace_minutes if schedule else 15
        late_boundary = (datetime.combine(day, schedule_start) + timedelta(minutes=grace)).time()
        if clock > late_boundary:
            status, event_type = "Late", "tardiness"
    event = AttendanceEvent(
        id=str(uuid.uuid4()), person_id=person.id, event_date=day, event_time=clock,
        direction=direction, status=status, recognition_distance=distance, source="Gate camera / LBPH",
    )
    db.add(event)
    db.commit()

    values = {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%Y-%m-%d"),
        "class_name": f"{schedule.subject} — Grade {schedule.grade} {schedule.section}" if isinstance(schedule, ClassSchedule) else person.role,
        "className": f"{schedule.subject} — Grade {schedule.grade} {schedule.section}" if isinstance(schedule, ClassSchedule) else person.role,
        "class_start": schedule_start.strftime("%I:%M %p") if schedule_start else "not configured",
        "classStart": schedule_start.strftime("%I:%M %p") if schedule_start else "not configured",
        "absence_cutoff": config["absence_cutoff"], "absenceCutoff": config["absence_cutoff"],
    }
    sms = queue_notice(db, person, event_type, values,
                       idempotency_key=f"attendance:{event.id}:{event_type}")
    return {
        "recorded": True,
        "id": event.id,
        "direction": direction,
        "status": status,
        "date": day.isoformat(),
        "time": clock.isoformat(timespec="seconds"),
        "sms_status": sms.status if sms else "not-applicable",
        "sms_id": sms.id if sms else None,
    }


def close_day(db: Session, day: date, grade: str | None = None, section: str | None = None,
              due_at: time | None = None) -> int:
    if not is_instructional_day(db, day):
        return 0
    count = 0
    people = active_people(db, grade, section, students_only=bool(grade or section))
    for person in people:
        # Personnel are absent only when an administrator has assigned a duty
        # schedule that applies to this date. This prevents unscheduled staff
        # from being marked absent by the school-wide daily close.
        if person.role != "Student" and not applicable_schedule(db, person, day):
            continue
        cutoff = person_absence_cutoff(db, person, day)
        if due_at is not None and due_at < cutoff:
            continue
        row = raw_row(db, person, day)
        if row["status"] != "No scan":
            continue
        event = AttendanceEvent(
            id=str(uuid.uuid4()), person_id=person.id, event_date=day, event_time=cutoff,
            direction="Daily Close", status="Absent", source="Authorized daily close",
        )
        db.add(event)
        db.commit()
        sms = queue_notice(db, person, "absence", {
            "time": cutoff.strftime("%H:%M"), "date": day.isoformat(), "class_name": f"Grade {person.grade} {person.section}",
            "className": f"Grade {person.grade} {person.section}", "class_start": "", "classStart": "",
            "absence_cutoff": cutoff.strftime("%H:%M"), "absenceCutoff": cutoff.strftime("%H:%M"),
        }, idempotency_key=f"attendance:{event.id}:absence")
        count += 1
    return count


def close_due_attendance(db: Session, day: date, current_time: time) -> int:
    """Close only people whose configured schedule cutoff has been reached."""
    return close_day(db, day, due_at=current_time)


def save_correction(db: Session, payload, actor: User) -> AttendanceCorrection:
    person = db.get(Person, payload.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    before = raw_row(db, person, payload.attendance_date)
    record = AttendanceCorrection(
        id=str(uuid.uuid4()), person_id=person.id, attendance_date=payload.attendance_date,
        status=payload.status, time_in=payload.time_in, time_out=payload.time_out, reason=payload.reason.strip(),
        actor_user_id=actor.id, actor_name=actor.full_name, actor_role=actor.role,
        before_json=json.dumps(before, default=str),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def reset_day(db: Session, day: date, reason: str, actor: User) -> AttendanceResetAudit:
    cutoff = datetime.utcnow()
    superseded_events = db.scalar(select(func.count(AttendanceEvent.id)).where(
        AttendanceEvent.event_date == day, AttendanceEvent.created_at <= cutoff,
    )) or 0
    superseded_corrections = db.scalar(select(func.count(AttendanceCorrection.id)).where(
        AttendanceCorrection.attendance_date == day, AttendanceCorrection.created_at <= cutoff,
    )) or 0
    audit = AttendanceResetAudit(
        id=str(uuid.uuid4()), attendance_date=day, reason=reason.strip(), actor_user_id=actor.id,
        actor_name=actor.full_name, actor_role=actor.role, superseded_event_count=superseded_events,
        superseded_correction_count=superseded_corrections, created_at=cutoff,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit
