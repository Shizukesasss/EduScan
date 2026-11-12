from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, time, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..config import EXPORT_DIR
from ..database import get_db
from ..models import (AttendanceCorrection, AttendanceEvent, AttendanceResetAudit, CalendarException,
                      DtrDutySchedule, ExcusedAbsence, Person, SchoolYear, User)
from .annex_g import annex_g_school_profile_data
from .attendance import (NOON, PUNCH_FIELDS, _attendance_row, applicable_schedule,
                         attendance_event_query, attendance_scans, local_now)
from .audit import add_audit
from .enrollment import enrollment_block
from .export_files import new_report_path
from .dtr_form import write_form48
from .reports import register_report
from .settings_store import get_json


DTR_REPORT_TYPE = 'Monthly Form 48'
PERSONNEL_ROLES = ('Faculty', 'Non-teaching Personnel')

admin_required = require_roles('admin')
router = APIRouter(prefix='/api/dtr', dependencies=[Depends(admin_required)])


class DutyHours(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode='after')
    def validate_hours(self):
        if self.start_time.tzinfo or self.end_time.tzinfo or self.start_time >= self.end_time:
            raise ValueError('Duty end must be after duty start on the same day, using local time.')
        return self


def _employee_data(person: Person) -> dict:
    return {'id': person.id, 'full_name': person.full_name, 'employee_id': person.external_id,
            'role': person.role, 'active': person.active}


def _employee(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if not person or person.role not in PERSONNEL_ROLES:
        raise HTTPException(404, 'Personnel record was not found.')
    return person


def _saved_hours(db: Session, person_id: int) -> list[DutyHours]:
    schedule = db.get(DtrDutySchedule, person_id)
    return [DutyHours.model_validate(row) for row in json.loads(schedule.hours_json)] if schedule else []


def _schedule_update(dialect: str, person_id: int, encoded: str):
    values = {'person_id': person_id, 'hours_json': encoded}
    if dialect in ('mysql', 'mariadb'):
        return mysql_insert(DtrDutySchedule).values(**values).on_duplicate_key_update(hours_json=encoded)
    insert = sqlite_insert if dialect == 'sqlite' else postgres_insert
    return insert(DtrDutySchedule).values(**values).on_conflict_do_update(
        index_elements=[DtrDutySchedule.person_id], set_={'hours_json': encoded},
    )


@router.get('/employees')
def employees(role: str, q: Annotated[str, Query(max_length=180)] = '', db: Session = Depends(get_db)):
    if role not in PERSONNEL_ROLES:
        raise HTTPException(422, 'Select Faculty or Non-teaching Personnel.')
    search = q.strip().casefold()
    people = db.scalars(select(Person).where(Person.role == role)
                        .order_by(Person.active.desc(), Person.full_name, Person.external_id))
    return [_employee_data(person) for person in people
            if search in person.full_name.casefold() or search in person.external_id.casefold()]


@router.get('/{person_id}/schedule')
def duty_hours(person_id: int, db: Session = Depends(get_db)) -> list[DutyHours]:
    _employee(db, person_id)
    return _saved_hours(db, person_id)


@router.put('/{person_id}/schedule')
def save_duty_hours(person_id: int, hours: Annotated[list[DutyHours], Field(max_length=7)],
                    db: Session = Depends(get_db), admin: User = Depends(admin_required)) -> list[DutyHours]:
    _employee(db, person_id)
    if len({row.weekday for row in hours}) != len(hours):
        raise HTTPException(422, 'Enter at most one duty schedule per weekday.')
    before = [row.model_dump(mode='json') for row in _saved_hours(db, person_id)]
    hours = sorted(hours, key=lambda row: row.weekday)
    after = [row.model_dump(mode='json') for row in hours]
    db.execute(_schedule_update(db.get_bind().dialect.name, person_id, json.dumps(after)))
    add_audit(db, admin, 'Update', 'DtrDutySchedule', person_id, 'Updated recurring Form 48 duty hours', before, after)
    db.commit()
    return hours


def _after_reset(item, reset: AttendanceResetAudit | None) -> bool:
    if reset is None:
        return True
    created_at = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=timezone.utc)
    cutoff = reset.created_at if reset.created_at.tzinfo else reset.created_at.replace(tzinfo=timezone.utc)
    return created_at > cutoff


def _monthly_data(db: Session, person: Person, year: int, month: int) -> dict:
    days = [date(year, month, day) for day in range(1, calendar.monthrange(year, month)[1] + 1)]
    now = local_now()
    elapsed = [day for day in days if day <= now.date()]
    resets = {}
    for reset in db.scalars(select(AttendanceResetAudit).where(AttendanceResetAudit.attendance_date.in_(elapsed))
                            .order_by(AttendanceResetAudit.created_at.desc())):
        resets.setdefault(reset.attendance_date, reset)
    events = defaultdict(list)
    for event in db.scalars(attendance_event_query().where(AttendanceEvent.person_id == person.id,
                            AttendanceEvent.event_date.in_(elapsed))
                            .order_by(AttendanceEvent.event_time, AttendanceEvent.created_at)):
        if _after_reset(event, resets.get(event.event_date)):
            events[event.event_date].append(event)
    corrections = {}
    for correction in db.scalars(select(AttendanceCorrection).where(AttendanceCorrection.person_id == person.id,
                                 AttendanceCorrection.attendance_date.in_(elapsed))
                                 .order_by(AttendanceCorrection.created_at.desc())):
        if _after_reset(correction, resets.get(correction.attendance_date)):
            corrections.setdefault(correction.attendance_date, correction)
    exceptions = {item.event_date: item for item in db.scalars(select(CalendarException)
                  .where(CalendarException.event_date.in_(days)))}
    excuses = {item.event_date: item for item in db.scalars(select(ExcusedAbsence).where(
               ExcusedAbsence.person_id == person.id, ExcusedAbsence.event_date.in_(elapsed)))}
    hours = {row.weekday: row for row in _saved_hours(db, person.id)}
    schedules = {day.weekday(): hours.get(day.weekday()) or applicable_schedule(db, person, day) for day in days[:7]}
    rows = []
    for day in days:
        exception = exceptions.get(day)
        day_events = events.get(day, [])
        schedule = schedules[day.weekday()]
        duty_hours = (schedule.start_time, schedule.end_time) if schedule else None
        row = (_attendance_row(person, day, day_events, corrections.get(day), resets.get(day),
                               exception, excuses.get(day), now=now, duty_hours=duty_hours)
               if day <= now.date() else None)
        blocked = enrollment_block(person, day)
        scans = attendance_scans(day_events, row, blocked=bool(blocked)) if row else []
        punches = {key: row[key] if row else None for key in PUNCH_FIELDS}
        non_duty = exception.event_type if exception and exception.event_type in ('Holiday', 'Suspended') else None
        start = schedule.start_time if schedule else None
        end = schedule.end_time if schedule else None
        special_duty = exception and exception.event_type == 'Special Schedule'
        if special_duty:
            start = exception.start_time or start
            end = exception.end_time or end
        missing = []
        review = None
        status = row['status'] if row else None
        if row and not blocked and not non_duty and status != 'Excused':
            if start is None or end is None or start >= end:
                if day.weekday() < 5 or scans or special_duty:
                    review = 'Duty hours need review'
            elif day < now.date() or now.time() >= end:
                expected = PUNCH_FIELDS[:2] if start < NOON else ()
                if end > NOON:
                    expected += PUNCH_FIELDS[2:]
                missing = [key for key in expected if punches[key] is None]
        marker = None
        if row and not scans and not blocked:
            if non_duty:
                marker = non_duty
            elif day.weekday() >= 5 and not schedule and not special_duty:
                marker = day.strftime('%a').upper()
        rows.append({'date': day, **punches, 'missing': missing, 'review': review,
                     'marker': marker, 'status': status,
                     'am_status': row['am_status'] if row else None,
                     'pm_status': row['pm_status'] if row else None})
    return {'employee': _employee_data(person), 'days': rows, 'year': year, 'month': month, 'schedules': schedules}


@router.get('/{person_id}/preview')
def preview(person_id: int, year: Annotated[int, Query(ge=1900, le=9999)],
            month: Annotated[int, Query(ge=1, le=12)], db: Session = Depends(get_db)):
    data = _monthly_data(db, _employee(db, person_id), year, month)
    return {'employee': data['employee'], 'days': data['days']}


@router.get('/{person_id}/export')
def export(person_id: int, year: Annotated[int, Query(ge=1900, le=9999)],
           month: Annotated[int, Query(ge=1, le=12)], format: Annotated[str, Query(pattern='^(pdf|xlsx)$')],
           db: Session = Depends(get_db), admin: User = Depends(admin_required)):
    data = _monthly_data(db, _employee(db, person_id), year, month)
    school = annex_g_school_profile_data(db)
    years = db.scalars(select(SchoolYear.id).where(SchoolYear.deleted_at.is_(None),
                       SchoolYear.starts_on <= data['days'][-1]['date'],
                       SchoolYear.ends_on >= data['days'][0]['date']).limit(2)).all()
    if len(years) == 1:
        school['head'] = get_json(db, 'school.heads', {}).get(str(years[0]), {}).get('full_name', '')
    data['school'] = school
    path = new_report_path(Path(EXPORT_DIR), f'Form-48-{person_id}-{year}-{month:02d}.{format}')
    try:
        write_form48(path, data)
        report = register_report(db, path, DTR_REPORT_TYPE, {
            'employee': data['employee']['full_name'], 'employee_id': data['employee']['employee_id'],
            'role': data['employee']['role'], 'year': year, 'month': month,
        }, admin)
    finally:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    media = 'application/pdf' if format == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return FileResponse(report.file_path, filename=report.filename, media_type=media,
                        headers={'Cache-Control': 'private, no-store'})
