from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from ..models import AttendanceCorrection, AttendanceEvent, AttendanceResetAudit, CalendarException, ClassSchedule, DtrDutySchedule, ExcusedAbsence, Person, PersonnelSchedule, User
from .settings_store import get_json
from .enrollment import enrollment_block, DEPARTURE_STATUSES
from .sms import queue_notice


MANILA = timezone(timedelta(hours=8), "Asia/Manila")
NOON = time(12)
PUNCH_FIELDS = ('am_arrival', 'am_departure', 'pm_arrival', 'pm_departure')
SESSION_WINDOWS = {
    'am': (time(7, 30), time(7, 46), time(11, 41)),
    'pm': (time(13), time(13, 16), time(16)),
}


def local_now() -> datetime:
    return datetime.now(MANILA)


def attendance_config(db: Session) -> dict:
    return {"absence_cutoff": "09:00", "duplicate_cooldown_seconds": 5, "auto_close_enabled": True,
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
    return _matching_personnel_schedule(person, day, schedules)


def _matching_personnel_schedule(person: Person, day: date, schedules: list[PersonnelSchedule]):
    eligible = [item for item in schedules if item.role == person.role and str(day.weekday()) in item.weekdays.split(",")]
    assignment = (person.assignment or "").strip().casefold()
    matching = [item for item in eligible if assignment and (item.assignment or "").strip().casefold() == assignment]
    defaults = [item for item in eligible if not (item.assignment or "").strip()]
    return next(iter(matching or defaults), None)


def _report_duty_hours(db: Session, people: list[Person], days: list[date]) -> dict:
    personnel = [person for person in people if person.role in {"Faculty", "Non-teaching Personnel"}]
    if not personnel:
        return {}
    schedules = db.scalars(select(PersonnelSchedule).where(PersonnelSchedule.active.is_(True))
                           .order_by(PersonnelSchedule.start_time)).all()
    overrides = {}
    for item in db.scalars(select(DtrDutySchedule).where(DtrDutySchedule.person_id.in_([p.id for p in personnel]))):
        overrides[item.person_id] = {
            row["weekday"]: (time.fromisoformat(row["start_time"]), time.fromisoformat(row["end_time"]))
            for row in json.loads(item.hours_json)
        }
    hours = {}
    for person in personnel:
        for day in days:
            custom = overrides.get(person.id, {}).get(day.weekday())
            schedule = None if custom else _matching_personnel_schedule(person, day, schedules)
            if custom or schedule:
                hours[(person.id, day)] = custom or (schedule.start_time, schedule.end_time)
    return hours


def _arrival_status(period: str, clock: time) -> str:
    _, late_from, closes_at = SESSION_WINDOWS[period]
    if clock >= closes_at:
        return "After cutoff"
    return "Late" if clock >= late_from else "Present"


def _scheduled_periods(person: Person, day: date, exception: CalendarException | None,
                       duty_hours: tuple[time, time] | None) -> set[str]:
    if exception and exception.event_type in {"Holiday", "Suspended"}:
        return set()
    special = exception if exception and exception.event_type == "Special Schedule" else None
    if not (duty_hours or special or (person.role == "Student" and day.weekday() < 5)):
        return set()
    start, end = duty_hours or (None, None)
    if special:
        start, end = special.start_time or start, special.end_time or end
    return {period for period, expected in (("am", start is None or start < NOON),
                                            ("pm", end is None or end > NOON)) if expected}


def _session_statuses(person: Person, day: date, row: dict, now: datetime,
                      exception: CalendarException | None, duty_hours: tuple[time, time] | None,
                      arrival_overrides: dict[time, str]) -> dict:
    status = row["status"]
    if status in {"Holiday", "Suspended", "Excused"} or enrollment_block(person, day):
        return dict.fromkeys(("am_status", "pm_status"), status)
    if exception and exception.event_type in {"Holiday", "Suspended"}:
        return dict.fromkeys(("am_status", "pm_status"), exception.event_type)
    scheduled = _scheduled_periods(person, day, exception, duty_hours)
    if status == "Weekend" and not scheduled:
        return dict.fromkeys(("am_status", "pm_status"), status)
    registered = getattr(person, "created_at", None)
    if registered and not (person.enrollment_start_date or row["am_arrival"] or row["pm_arrival"]):
        registered = (registered.replace(tzinfo=timezone.utc) if registered.tzinfo is None else registered).astimezone(MANILA)
    else:
        registered = None
    result = {}
    for period, (_, _, cutoff) in SESSION_WINDOWS.items():
        arrival = row[f"{period}_arrival"]
        expected = period in scheduled
        closed = day < now.date() or (day == now.date() and now.time() >= cutoff)
        arrival_status = (arrival_overrides.get(arrival) or _arrival_status(period, arrival)
                          if arrival is not None else None)
        if status == "Absent" and row["correction_reason"] is not None and expected:
            value = "Absent"
        elif arrival_status in {"Present", "Late"}:
            value = arrival_status
        elif not expected or (registered and registered > datetime.combine(day, cutoff, MANILA)):
            value = "Not scheduled"
        elif not closed:
            value = "Pending"
        elif row["correction_reason"] is not None and status in {"Present", "Late"} and not row["time_in"]:
            value = "Needs review"
        else:
            value = "Absent"
        result[f"{period}_status"] = value
    return result


def latest_day_reset(db: Session, day: date) -> AttendanceResetAudit | None:
    return db.scalar(
        select(AttendanceResetAudit).where(AttendanceResetAudit.attendance_date == day)
        .order_by(AttendanceResetAudit.created_at.desc())
    )


def attendance_event_query():
    cleared = select(AttendanceCorrection.id).where(
        AttendanceCorrection.person_id == AttendanceEvent.person_id,
        AttendanceCorrection.attendance_date == AttendanceEvent.event_date,
        AttendanceCorrection.status == "No scan",
        AttendanceCorrection.created_at >= AttendanceEvent.created_at,
    ).exists()
    return select(AttendanceEvent).where(~cleared)


def raw_row(db: Session, person: Person, day: date) -> dict:
    reset = latest_day_reset(db, day)
    event_query = attendance_event_query().where(AttendanceEvent.person_id == person.id, AttendanceEvent.event_date == day)
    if reset:
        event_query = event_query.where(AttendanceEvent.created_at > reset.created_at)
    events = db.scalars(event_query.order_by(AttendanceEvent.event_time, AttendanceEvent.created_at)).all()
    exception = calendar_exception(db, day)
    excused = db.scalar(select(ExcusedAbsence).where(
        ExcusedAbsence.person_id == person.id, ExcusedAbsence.event_date == day,
    ))
    correction_query = select(AttendanceCorrection).where(
        AttendanceCorrection.person_id == person.id,
        AttendanceCorrection.attendance_date == day,
    )
    if reset:
        correction_query = correction_query.where(AttendanceCorrection.created_at > reset.created_at)
    correction = db.scalar(correction_query.order_by(AttendanceCorrection.created_at.desc()))
    hours = _report_duty_hours(db, [person], [day])
    return _attendance_row(person, day, events, correction, reset, exception, excused,
                           duty_hours=hours.get((person.id, day)))


def _period_punches(scans: list[tuple[str, time]]) -> dict[str, time | None]:
    result = dict.fromkeys(PUNCH_FIELDS)
    morning_visit_open = False
    afternoon_start = SESSION_WINDOWS["pm"][0]
    for direction, clock in sorted(scans, key=lambda scan: scan[1]):
        period = 'am' if clock < NOON else 'pm'
        # A lunch checkout can close an open morning visit after noon.
        if direction == 'Time Out' and clock < afternoon_start and morning_visit_open and not result['pm_arrival']:
            period = 'am'
        if period == 'am':
            morning_visit_open = direction == 'Time In'
        if direction == 'Time In':
            key = f'{period}_arrival'
            if result[key] is None:
                result[key] = clock
        else:
            result[f'{period}_departure'] = clock
    return result


def _corrected_scans(scans: list[tuple[str, time]], row: dict) -> list[tuple[str, time]]:
    start, end = row['time_in'], row['time_out']
    corrected = [(direction, clock) for direction, clock in [('Time In', start), ('Time Out', end)]
                 if clock is not None]
    if row['status'] not in ('Present', 'Late') or start is None or end is None or start >= end:
        return corrected

    # Daily corrections replace the outside punches. Keep recorded midday punches within those bounds.
    first_in = next((clock for direction, clock in scans if direction == 'Time In'), None)
    last_out = next((clock for direction, clock in reversed(scans) if direction == 'Time Out'), None)
    return corrected + [(direction, clock) for direction, clock in scans
                        if start < clock < end and (direction, clock) not in (('Time In', first_in), ('Time Out', last_out))]


def attendance_scans(events: list[AttendanceEvent], row: dict, *, blocked: bool) -> list[tuple[str, time]]:
    scans = [(event.direction, event.event_time) for event in events
             if not blocked and event.direction in ("Time In", "Time Out")]
    if row["correction_reason"] is not None:
        return _corrected_scans(scans, row)
    return scans


def _attendance_row(person: Person, day: date, events: list[AttendanceEvent],
                    correction: AttendanceCorrection | None, reset: AttendanceResetAudit | None,
                    exception: CalendarException | None, excused: ExcusedAbsence | None, *,
                    now: datetime | None = None, duty_hours: tuple[time, time] | None = None) -> dict:
    time_in_event = next((event for event in events if event.direction == "Time In"), None)
    arrival_overrides = {event.event_time: event.status for event in events
                         if event.direction == "Time In" and event.status_overridden
                         and event.status in {"Present", "Late"}}
    arrival_statuses = (arrival_overrides.get(event.event_time)
                        or _arrival_status("am" if event.event_time < NOON else "pm", event.event_time)
                        for event in events if event.direction == "Time In")
    qualifying_status = next((status for status in arrival_statuses if status != "After cutoff"), None)
    time_out_event = next((event for event in reversed(events) if event.direction == "Time Out"), None)
    last_gate_event = next((event for event in reversed(events) if event.direction in {"Time In", "Time Out"}), None)
    absence_event = next((event for event in events if event.status == "Absent"), None)
    status = "No scan"
    source = f"Clean slate started by {reset.actor_name}" if reset else "—"
    blocked = enrollment_block(person, day)
    if blocked:
        status, source = blocked, f"Enrollment / service period: {person.enrollment_start_date or 'start not recorded'} to {person.enrollment_end_date or 'end not recorded'}"
    elif qualifying_status:
        status = qualifying_status
        source = last_gate_event.source
    elif excused:
        status, source = "Excused", f"Excused by {excused.actor_name}"
    elif exception and exception.event_type in {"Holiday", "Suspended"}:
        status, source = exception.event_type, exception.reason
    elif day.weekday() >= 5:
        status, source = "Weekend", "Non-instructional day"
    elif absence_event:
        status, source = "Absent", absence_event.source
    row = {
        "person_id": person.id,
        "external_id": person.external_id,
        "lrn": person.lrn,
        "full_name": person.full_name,
        "sex": person.sex,
        "role": person.role,
        "grade": person.grade,
        "section": person.section,
        "assignment": person.assignment,
        "enrollment_status": person.enrollment_status,
        "enrollment_note": person.enrollment_note,
        "enrollment_start_date": person.enrollment_start_date,
        "enrollment_end_date": person.enrollment_end_date,
        "transfer_school": person.transfer_school,
        "time_in": time_in_event.event_time if time_in_event else None,
        "time_out": time_out_event.event_time if time_out_event else None,
        "last_gate_time": last_gate_event.event_time if last_gate_event else None,
        "last_gate_direction": last_gate_event.direction if last_gate_event else None,
        "status": status,
        "source": source,
        "correction_reason": None,
    }
    # A cleared accidental scan must not override a later genuine gate visit.
    if correction and not blocked and (correction.status != "No scan" or not events):
        row.update(time_in=correction.time_in, time_out=correction.time_out, status=correction.status,
                   source=f"Corrected by {correction.actor_name}", correction_reason=correction.reason)
        if correction.status == "Time Out":
            row["status"] = "Late" if time_in_event and time_in_event.status == "Late" else "Present"
    row.update(_period_punches(attendance_scans(events, row, blocked=bool(blocked))))
    row.update(_session_statuses(person, day, row, now or local_now(), exception, duty_hours, arrival_overrides))
    return row


def _identity_key(person: Person) -> str:
    identifier = person.lrn if person.role == "Student" and person.lrn else person.external_id
    return f"{person.role.casefold()}:{identifier.strip().casefold()}"


def active_people(db: Session, grade: str | None = None, section: str | None = None,
                  students_only: bool = False, include_departed: bool = False) -> list[Person]:
    eligible = Person.active.is_(True)
    if include_departed:
        eligible = or_(eligible, Person.enrollment_status.in_(DEPARTURE_STATUSES), Person.enrollment_end_date.is_not(None))
    query = select(Person).where(eligible)
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
    people = active_people(db, grade, section, students_only, include_departed=True)
    return rows_for_people(db, people, day)


def rows_for_people(db: Session, people: list[Person], day: date) -> list[dict]:
    if not people:
        return []
    ids = [person.id for person in people]
    reset = latest_day_reset(db, day)
    events_query = attendance_event_query().where(AttendanceEvent.person_id.in_(ids), AttendanceEvent.event_date == day)
    corrections_query = select(AttendanceCorrection).where(AttendanceCorrection.person_id.in_(ids), AttendanceCorrection.attendance_date == day)
    if reset:
        events_query = events_query.where(AttendanceEvent.created_at > reset.created_at)
        corrections_query = corrections_query.where(AttendanceCorrection.created_at > reset.created_at)
    events_by_person = {person.id: [] for person in people}
    for event in db.scalars(events_query.order_by(AttendanceEvent.event_time, AttendanceEvent.created_at)):
        events_by_person[event.person_id].append(event)
    corrections = {}
    for correction in db.scalars(corrections_query.order_by(AttendanceCorrection.created_at.desc())):
        corrections.setdefault(correction.person_id, correction)
    exception = calendar_exception(db, day)
    excuses = {item.person_id: item for item in db.scalars(select(ExcusedAbsence).where(
        ExcusedAbsence.person_id.in_(ids), ExcusedAbsence.event_date == day))}
    hours = _report_duty_hours(db, people, [day])
    now = local_now()
    return [_attendance_row(person, day, events_by_person[person.id], corrections.get(person.id),
                            reset, exception, excuses.get(person.id), now=now,
                            duty_hours=hours.get((person.id, day))) for person in people]


def rows_for_people_on_days(db: Session, people: list[Person], days: list[date]) -> dict[date, list[dict]]:
    """Read a reporting period with batched attendance and duty schedule queries."""
    if not people or not days:
        return {day: [] for day in days}
    ids = [person.id for person in people]
    resets = {}
    for reset in db.scalars(select(AttendanceResetAudit).where(
            AttendanceResetAudit.attendance_date.in_(days)).order_by(AttendanceResetAudit.created_at.desc())):
        resets.setdefault(reset.attendance_date, reset)

    def after_reset(item, day):
        reset = resets.get(day)
        if not reset:
            return True
        def utc(value):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc(item.created_at) > utc(reset.created_at)

    events = {}
    for item in db.scalars(attendance_event_query().where(
            AttendanceEvent.person_id.in_(ids), AttendanceEvent.event_date.in_(days))
            .order_by(AttendanceEvent.event_time, AttendanceEvent.created_at)):
        if after_reset(item, item.event_date):
            events.setdefault((item.event_date, item.person_id), []).append(item)
    corrections = {}
    for item in db.scalars(select(AttendanceCorrection).where(
            AttendanceCorrection.person_id.in_(ids), AttendanceCorrection.attendance_date.in_(days))
            .order_by(AttendanceCorrection.created_at.desc())):
        if after_reset(item, item.attendance_date):
            corrections.setdefault((item.attendance_date, item.person_id), item)
    exceptions = {item.event_date: item for item in db.scalars(select(CalendarException).where(
        CalendarException.event_date.in_(days)))}
    excuses = {(item.event_date, item.person_id): item for item in db.scalars(select(ExcusedAbsence).where(
        ExcusedAbsence.person_id.in_(ids), ExcusedAbsence.event_date.in_(days)))}
    hours = _report_duty_hours(db, people, days)
    now = local_now()
    return {day: [_attendance_row(person, day, events.get((day, person.id), []),
                    corrections.get((day, person.id)), resets.get(day), exceptions.get(day),
                    excuses.get((day, person.id)), now=now,
                    duty_hours=hours.get((person.id, day))) for person in people] for day in days}


def record_gate_match(db: Session, person: Person, distance: float, now: datetime | None = None,
                      *, identity_matcher: str = 'LBPH') -> dict:
    now = now or local_now()
    day, clock = now.date(), now.timetz().replace(tzinfo=None)
    blocked = enrollment_block(person, day)
    if not person.active or blocked:
        return {"recorded": False, "status": blocked or "Inactive", "message": f"No attendance recorded: {blocked or 'Inactive school record'}"}
    config = attendance_config(db)
    reset = latest_day_reset(db, day)
    day_events_query = attendance_event_query().where(
        AttendanceEvent.person_id == person.id,
        AttendanceEvent.event_date == day,
        AttendanceEvent.direction.in_(["Time In", "Time Out"]),
    )
    if reset:
        day_events_query = day_events_query.where(AttendanceEvent.created_at > reset.created_at)
    day_events = db.scalars(day_events_query.order_by(AttendanceEvent.created_at, AttendanceEvent.event_time)).all()
    recent = day_events[-1] if day_events else None
    utc_now = datetime.utcnow()
    if recent and (utc_now - recent.created_at).total_seconds() < int(config["duplicate_cooldown_seconds"]):
        remaining = int(config["duplicate_cooldown_seconds"] - (utc_now - recent.created_at).total_seconds())
        return {"recorded": False, "message": f"Duplicate scan ignored; try again in {max(1, remaining)} seconds"}
    period = "am" if clock < NOON else "pm"
    period_events = [item for item in day_events if (item.event_time < NOON) == (period == "am")]
    last_in_period = period_events[-1] if period_events else None
    # A noon checkout can close the morning visit. After the PM arrival cutoff,
    # a lone open morning visit can still be closed by a departure scan.
    if not last_in_period and recent and recent.direction == "Time In" and (
        clock == NOON or clock >= SESSION_WINDOWS["pm"][2]
    ):
        last_in_period = recent
    direction = "Time Out" if last_in_period and last_in_period.direction == "Time In" else "Time In"
    first_arrival = direction == "Time In" and not any(item.direction == "Time In" for item in period_events)
    schedule = applicable_schedule(db, person, day) if first_arrival else None
    status = "Present" if direction == "Time In" else "Time Out"
    event_type = "time_in" if direction == "Time In" else "time_out"
    schedule_start, _, closes_at = SESSION_WINDOWS[period]
    if direction == "Time In":
        status = _arrival_status(period, clock)
        if status == "Late" and first_arrival:
            event_type = "tardiness"
    event = AttendanceEvent(
        id=str(uuid.uuid4()), person_id=person.id, event_date=day, event_time=clock,
        direction=direction, status=status, recognition_distance=distance, source=f"Gate camera / {identity_matcher}",
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
        "absence_cutoff": closes_at.strftime("%H:%M"), "absenceCutoff": closes_at.strftime("%H:%M"),
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
    hours = _report_duty_hours(db, people, [day])
    exception = calendar_exception(db, day)
    for person in people:
        periods = _scheduled_periods(person, day, exception, hours.get((person.id, day)))
        if not periods:
            continue
        session_cutoff = max(SESSION_WINDOWS[period][2] for period in periods)
        cutoff = person_absence_cutoff(db, person, day)
        if due_at is not None:
            cutoff = max(cutoff, session_cutoff)
        if due_at is not None and due_at < cutoff:
            continue
        # Registration alone must not backdate absence to an earlier cutoff.
        if not person.enrollment_start_date and person.created_at:
            registered_at = person.created_at
            if registered_at.tzinfo is None:
                registered_at = registered_at.replace(tzinfo=timezone.utc)
            if registered_at > datetime.combine(day, min(cutoff, session_cutoff), MANILA):
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
    if enrollment_block(person, payload.attendance_date) and payload.status != "No scan":
        raise HTTPException(status_code=422, detail="Attendance must be within the enrolled / duty period; correct the school-record dates first")
    if payload.status == "No scan" and (payload.time_in or payload.time_out):
        raise HTTPException(status_code=422, detail="A No scan correction must clear both attendance times")
    reason = payload.reason.strip()
    if payload.assisted:
        if not person.active or not payload.identity_verified:
            raise HTTPException(status_code=422, detail="Verify the active person's school ID or official roster before assisted attendance")
        if payload.status not in {"Present", "Late"} or not payload.time_in:
            raise HTTPException(status_code=422, detail="Assisted attendance requires the verified arrival time and Present or Late status under the existing school rules")
        if payload.time_out and payload.time_out < payload.time_in:
            raise HTTPException(status_code=422, detail="Departure time cannot be before arrival time")
        if len(reason) < 8:
            raise HTTPException(status_code=422, detail="Document the reason for staff assistance (at least 8 characters)")
        reason = f"Staff-assisted attendance (school ID/roster verified): {reason}"
    before = raw_row(db, person, payload.attendance_date)
    record = AttendanceCorrection(
        id=str(uuid.uuid4()), person_id=person.id, attendance_date=payload.attendance_date,
        status=payload.status, time_in=payload.time_in, time_out=payload.time_out, reason=reason,
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
