"""Roster and scanner attendance regressions, isolated from school records."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

TEST_DIR = tempfile.TemporaryDirectory(prefix="eduscan-attendance-sync-", dir=os.environ.get("EDUSCAN_TEST_TEMP_DIR"))
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EDUSCAN_DATA_DIR"] = TEST_DIR.name
os.environ["EDUSCAN_SECRET_KEY"] = "isolated-attendance-sync-tests"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"
os.environ["SMS_GATEWAY_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import AttendanceCorrection, AttendanceEvent, CalendarException, ClassSchedule, ExcusedAbsence, GradeLevel, Person, PersonnelSchedule, SchoolSection, SchoolYear, SectionAdviserAssignment, User
from app.services.attendance import MANILA, close_due_attendance, list_rows, raw_row, record_gate_match, reset_day
from app.services.settings_store import set_json
from app.services import reports


class AttendanceSyncTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = User(username="admin", role="admin", full_name="Admin", password_hash="unused", must_change_password=False)
        self.teacher = User(username="teacher", role="teacher", full_name="Teacher", password_hash="unused", must_change_password=False)
        self.student = Person(external_id="STUDENT", full_name="Test Student", role="Student", sex="Male", grade="10", section="Rizal", biometric_consent=True)
        self.personnel = Person(external_id="STAFF", full_name="Test Staff", role="Faculty", sex="Female")
        self.grade = GradeLevel(name="10")
        self.db.add_all([self.admin, self.teacher, self.student, self.personnel, self.grade])
        self.db.flush()
        section = SchoolSection(grade_level_id=self.grade.id, name="Rizal", adviser_user_id=self.teacher.id)
        year = SchoolYear(name="2026-2027", starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
        self.db.add_all([section, year])
        self.db.flush()
        self.school_year = year
        self.db.add(SectionAdviserAssignment(school_year_id=year.id, section_id=section.id, teacher_user_id=self.teacher.id))
        self.db.commit()
        set_json(self.db, "attendance", {"duplicate_cooldown_seconds": 0, "auto_close_enabled": False})
        self.day = date(2026, 10, 13)
        def session_override():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = session_override
        self.client = TestClient(app)
        self.admin_headers = {"Authorization": f"Bearer {create_token(self.admin)}"}
        self.teacher_headers = {"Authorization": f"Bearer {create_token(self.teacher)}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def scan(self, hour, minute=0):
        return record_gate_match(self.db, self.student, 25, datetime.combine(self.day, time(hour, minute), MANILA))

    def api_rows(self, headers=None):
        response = self.client.get(f"/api/attendance?date={self.day}", headers=headers or self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def student_row(self):
        return next(row for row in self.api_rows() if row["person_id"] == self.student.id)

    def test_early_afternoon_scan_starts_session_even_without_morning_checkout(self):
        self.assertEqual(self.scan(7, 20)["status"], "Present")
        result = self.scan(12, 55)
        self.assertEqual(result["direction"], "Time In")
        self.assertEqual(result["status"], "Present")
        self.assertEqual(self.scan(16)["direction"], "Time Out")
        row = self.student_row()
        self.assertEqual((row["am_status"], row["pm_status"]), ("Present", "Present"))
        self.assertIsNone(row["am_departure"])

    def test_saved_lunch_checkout_closes_open_morning_visit(self):
        for index, clock, direction, status in (
            (1, time(7, 45, 45), "Time In", "Late"),
            (2, time(12, 52), "Time Out", "Time Out"),
            (3, time(12, 57), "Time Out", "Time Out"),
        ):
            self.db.add(AttendanceEvent(id=f"saved-{index}", person_id=self.student.id,
                                        event_date=self.day, event_time=clock, direction=direction, status=status))
        self.db.commit()
        row = raw_row(self.db, self.student, self.day)
        self.assertEqual(row["am_departure"], time(12, 52))
        self.assertIsNone(row["pm_arrival"])
        self.assertEqual(row["pm_departure"], time(12, 57))
        self.assertEqual(row["last_gate_direction"], "Time Out")
        self.assertEqual(row["status"], row["am_status"])

    def test_session_statuses_use_independent_cutoffs(self):
        self.student.enrollment_start_date = self.day
        self.db.commit()
        self.assertEqual(self.scan(13, 16)["status"], "Late")
        row = self.student_row()
        self.assertEqual((row["am_status"], row["pm_status"]), ("Absent", "Late"))

    def test_verified_late_arrival_overrides_only_its_session(self):
        morning = AttendanceEvent(id="verified-late", person_id=self.student.id,
                                  event_date=self.day, event_time=time(11, 53), direction="Time In", status="Late")
        afternoon = AttendanceEvent(id="afternoon-arrival", person_id=self.student.id,
                                    event_date=self.day, event_time=time(12, 57), direction="Time In", status="Present")
        self.db.add_all([morning, afternoon])
        self.db.commit()
        row = raw_row(self.db, self.student, self.day)
        self.assertEqual((row["am_status"], row["pm_status"], row["status"]), ("Absent", "Present", "Present"))

        morning.status_overridden = True
        self.db.commit()
        row = raw_row(self.db, self.student, self.day)
        self.assertEqual((row["am_status"], row["pm_status"], row["status"]), ("Late", "Present", "Late"))
        self.assertEqual((row["am_arrival"], row["pm_arrival"]), (time(11, 53), time(12, 57)))

    def test_pending_afternoon_becomes_absent_after_cutoff_for_all_roles(self):
        self.student.enrollment_start_date = self.personnel.enrollment_start_date = self.day
        support = Person(external_id="SUPPORT", full_name="Support Staff", role="Non-teaching Personnel",
                         sex="Female", enrollment_start_date=self.day)
        self.db.add(support)
        for role in (self.personnel.role, support.role):
            self.db.add(PersonnelSchedule(role=role, weekdays="1", start_time=time(7, 30), end_time=time(16)))
        self.db.commit()
        for person in (self.student, self.personnel, support):
            for clock, status in ((time(7, 45, 59), "Present"), (time(11, 40), "Time Out")):
                result = record_gate_match(self.db, person, 25, datetime.combine(self.day, clock, MANILA))
                self.assertEqual(result["status"], status)
        for clock, pm_status in ((time(15, 59, 59), "Pending"), (time(16), "Absent")):
            with patch("app.services.attendance.local_now", return_value=datetime.combine(self.day, clock, MANILA)):
                rows = self.api_rows()
            self.assertEqual({row["role"] for row in rows}, {"Student", "Faculty", "Non-teaching Personnel"})
            self.assertTrue(all((row["am_status"], row["pm_status"]) == ("Present", pm_status) for row in rows))

    def test_student_attendance_and_sf2_preview_show_four_punches_for_the_selected_day(self):
        for hour, minute in [(7, 30), (11, 55), (12, 40), (16, 0)]:
            self.scan(hour, minute)

        response = self.client.get(
            "/api/sf2/preview",
            params={"year": self.day.year, "month": self.day.month, "grade": "10",
                    "section": "Rizal", "attendance_date": self.day.isoformat()},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["preview_date"], self.day.isoformat())
        for row in [self.student_row(), response.json()["rows"][0]]:
            self.assertEqual(row["status"], "Present")
            self.assertEqual(row["am_arrival"], "07:30:00")
            self.assertEqual(row["am_departure"], "11:55:00")
            self.assertEqual(row["pm_arrival"], "12:40:00")
            self.assertEqual(row["pm_departure"], "16:00:00")

    def test_section_log_exports_recorded_punches_and_leaves_missing_punches_blank(self):
        for hour, minute in [(7, 30), (11, 55), (12, 40)]:
            self.scan(hour, minute)
        response = self.client.get(
            "/api/attendance/temporary-log",
            params={"date": self.day.isoformat(), "grade": "10", "section": "Rizal", "format": "xlsx"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        try:
            headers, student = workbook.active.values
            record = dict(zip(headers, student))
            self.assertEqual(record["AM Time In"], time(7, 30))
            self.assertEqual(record["AM Time Out"], time(11, 55))
            self.assertEqual(record["PM Time In"], time(12, 40))
            self.assertIsNone(record["PM Time Out"])
        finally:
            workbook.close()

    def test_student_punches_respect_daily_corrections_and_clean_slate(self):
        for hour, minute in [(7, 30), (11, 55), (12, 40), (16, 0)]:
            self.scan(hour, minute)
        response = self.client.post("/api/attendance/corrections", headers=self.admin_headers, json={
            "person_id": self.student.id, "attendance_date": self.day.isoformat(),
            "status": "Present", "time_in": "07:45", "time_out": "16:15",
            "reason": "Verified arrival and departure",
        })
        self.assertEqual(response.status_code, 200, response.text)
        row = self.student_row()
        keys = ("am_arrival", "am_departure", "pm_arrival", "pm_departure")
        self.assertEqual([row[key] for key in keys], ["07:45:00", "11:55:00", "12:40:00", "16:15:00"])
        reset_day(self.db, self.day, "Clear test attendance", self.admin)
        row = self.student_row()
        self.assertEqual([row[key] for key in keys], [None, None, None, None])

    def test_assisted_attendance_requires_identity_times_and_a_specific_reason(self):
        payload = {'person_id': self.student.id, 'attendance_date': str(self.day), 'status': 'Present',
                   'time_in': '07:30', 'assisted': True, 'identity_verified': True, 'reason': 'Camera verification could not be completed'}
        for changes in ({'identity_verified': False}, {'time_in': None}, {'status': 'Absent'},
                        {'reason': '        '}, {'time_out': '07:00'}):
            with self.subTest(changes=changes):
                response = self.client.post('/api/attendance/corrections', headers=self.admin_headers, json={**payload, **changes})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.scalars(select(AttendanceCorrection)).all(), [])
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])

    def test_assisted_attendance_is_audited_without_needing_biometrics(self):
        self.student.biometric_consent = False
        self.db.commit()
        self.scan(7)
        response = self.client.post('/api/attendance/corrections', headers=self.teacher_headers, json={
            'person_id': self.student.id, 'attendance_date': str(self.day), 'status': 'Late', 'time_in': '08:30',
            'assisted': True, 'identity_verified': True, 'reason': 'School roster verified in person; camera capture was unsuccessful',
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['actor_name'], self.teacher.full_name)
        self.assertIn('Staff-assisted attendance (school ID/roster verified)', response.json()['reason'])
        row = self.student_row()
        self.assertEqual(row['status'], 'Late')
        self.assertEqual(row['time_in'], '08:30:00')
        self.assertEqual(row['source'], 'Corrected by Teacher')
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)

    def test_assisted_attendance_keeps_existing_role_and_adviser_restrictions(self):
        scanner = User(username='scanner', role='scanner', full_name='Gate Scanner', password_hash='unused', must_change_password=False)
        self.db.add(scanner)
        self.db.commit()
        payload = {'person_id': self.personnel.id, 'attendance_date': str(self.day), 'status': 'Present', 'time_in': '07:30',
                   'assisted': True, 'identity_verified': True, 'reason': 'School identity verified in person'}
        for headers in (self.teacher_headers, {'Authorization': f'Bearer {create_token(scanner)}'}):
            response = self.client.post('/api/attendance/corrections', headers=headers, json=payload)
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.scalars(select(AttendanceCorrection)).all(), [])

    def test_first_time_in_is_visible_as_present_with_identity_and_class(self):
        result = self.scan(7, 30)
        self.assertTrue(result["recorded"])
        row = self.student_row()
        self.assertEqual(row["status"], "Present")
        self.assertEqual(row["time_in"], "07:30:00")
        self.assertEqual(row["external_id"], self.student.external_id)
        self.assertEqual((row["grade"], row["section"]), ("10", "Rizal"))

    def test_time_out_preserves_presence_and_both_scan_times(self):
        self.scan(7, 30)
        result = self.scan(16)
        self.assertEqual(result["direction"], "Time Out")
        row = self.student_row()
        self.assertEqual(row["status"], "Present")
        self.assertEqual((row["time_in"], row["time_out"]), ("07:30:00", "16:00:00"))
        self.assertEqual(self.db.scalar(select(AttendanceEvent).where(AttendanceEvent.direction == "Time Out")).status, "Time Out")

    def test_late_arrival_remains_late_after_checkout(self):
        self.db.add(ClassSchedule(grade="10", section="Rizal", subject="Math", teacher_name="Teacher", weekdays="1", start_time=time(7, 30), end_time=time(8, 30), late_grace_minutes=15))
        self.db.commit()
        self.scan(8, 15)
        self.scan(16)
        self.assertEqual(self.student_row()["status"], "Late")

    def test_successive_gate_visits_alternate_automatically(self):
        self.assertEqual(self.scan(7, 30)['direction'], 'Time In')
        self.assertEqual(self.scan(12)['direction'], 'Time Out')
        self.assertEqual(self.scan(13)['direction'], 'Time In')
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 3)

    def test_attendance_row_exposes_latest_gate_movement_after_reentry(self):
        self.scan(7, 30)
        self.scan(12)
        self.scan(13)
        row = self.student_row()
        self.assertEqual(row['last_gate_time'], '13:00:00')
        self.assertEqual(row['last_gate_direction'], 'Time In')

    def test_new_registration_appears_without_creating_a_false_attendance_event(self):
        invalid = self.client.post("/api/persons", headers=self.admin_headers, json={
            "external_id": "INVALID-PLACEMENT", "first_name": "Learner", "sex": "Female",
            "role": "Student", "grade": "10", "section": "Unknown",
        })
        self.assertEqual(invalid.status_code, 422, invalid.text)
        created = self.client.post("/api/persons", headers=self.admin_headers, json={
            "external_id": "NEW-STUDENT", "surname": "New", "first_name": "Learner", "sex": "Female", "date_of_birth": "2012-01-01", "role": "Student", "grade": "10", "section": "Rizal", "school_year_id": self.school_year.id, "enrollment_start_date": "2026-06-01", "biometric_consent": False})
        self.assertEqual(created.status_code, 200, created.text)
        row = next(row for row in self.api_rows() if row["person_id"] == created.json()["id"])
        self.assertEqual(row["status"], "No scan")
        self.assertIsNone(row["time_in"])
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])

    def test_enrollment_after_midnight_cutoff_does_not_create_immediate_absence(self):
        set_json(self.db, "attendance", {"absence_cutoff": "00:00"})
        self.student.created_at = datetime(2026, 10, 12, 17, 39)  # 01:39 the next day in Manila.
        self.db.commit()
        self.assertEqual(close_due_attendance(self.db, self.day, time(1, 40)), 0)
        self.assertEqual(raw_row(self.db, self.student, self.day)["status"], "No scan")
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])
        self.assertEqual(close_due_attendance(self.db, self.day + timedelta(days=1), time(16)), 1)

    def test_registration_before_cutoff_keeps_normal_absence_rule(self):
        self.student.created_at = datetime(2026, 10, 12, 23)  # 07:00 in Manila.
        self.db.commit()
        self.assertEqual(close_due_attendance(self.db, self.day, time(15, 59, 59)), 0)
        self.assertEqual(close_due_attendance(self.db, self.day, time(16)), 1)
        self.assertEqual(raw_row(self.db, self.student, self.day)["status"], "Absent")

    def test_later_daily_close_does_not_mark_people_registered_after_both_sessions(self):
        set_json(self.db, "attendance", {"absence_cutoff": "17:00"})
        self.student.created_at = datetime(2026, 10, 13, 8, 30)  # 4:30 PM in Manila.
        self.db.commit()
        self.assertEqual(close_due_attendance(self.db, self.day, time(17)), 0)

    def test_explicit_academic_enrollment_date_allows_backdated_roster_closing(self):
        self.student.created_at = datetime(2026, 10, 14)
        self.student.enrollment_start_date = self.day
        self.db.commit()
        self.assertEqual(close_due_attendance(self.db, self.day - timedelta(days=1), time(16)), 0)
        self.assertEqual(close_due_attendance(self.db, self.day, time(16)), 1)

    def test_no_scan_correction_clears_only_old_events_and_next_visit_starts_with_time_in(self):
        self.scan(7, 30)
        response = self.client.post("/api/attendance/corrections", headers=self.admin_headers, json={
            "person_id": self.student.id, "attendance_date": self.day.isoformat(), "status": "No scan",
            "time_in": None, "time_out": None, "reason": "Enrollment only; accidental attendance superseded",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.student_row()["status"], self.student_row()["time_in"]), ("No scan", None))
        self.assertEqual(reports.attendance_range_rows(self.db, self.day, self.day, grade="10", section="Rizal")[0]["status"], "No scan")
        for endpoint in ("gate/recent", "dashboard"):
            result = self.client.get(f"/api/{endpoint}?date={self.day}", headers=self.admin_headers)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json() if endpoint == "gate/recent" else result.json()["events"], [])
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)
        self.assertEqual(self.scan(8)["direction"], "Time In")
        self.assertEqual((self.student_row()["status"], self.student_row()["time_in"]), ("Late", "08:00:00"))
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 2)

    def test_no_scan_correction_rejects_attendance_times(self):
        response = self.client.post("/api/attendance/corrections", headers=self.admin_headers, json={
            "person_id": self.student.id, "attendance_date": self.day.isoformat(), "status": "No scan",
            "time_in": "08:00", "reason": "Accidental gate observation during enrollment",
        })
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.scalars(select(AttendanceCorrection)).all(), [])

    def test_no_scan_correction_preserves_other_people_and_dates(self):
        self.scan(7, 30)
        record_gate_match(self.db, self.personnel, 25, datetime.combine(self.day, time(7, 30), MANILA))
        tomorrow = self.day + timedelta(days=1)
        record_gate_match(self.db, self.student, 25, datetime.combine(tomorrow, time(7, 30), MANILA))
        response = self.client.post("/api/attendance/corrections", headers=self.admin_headers, json={
            "person_id": self.student.id, "attendance_date": self.day.isoformat(), "status": "No scan",
            "reason": "Enrollment-only visit corrected without deleting raw events",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(raw_row(self.db, self.personnel, self.day)["status"], "Present")
        self.assertEqual(raw_row(self.db, self.student, tomorrow)["status"], "Present")
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 3)

    def test_authorized_correction_still_controls_reported_attendance(self):
        self.scan(7, 30)
        self.db.add(AttendanceCorrection(id="correction", person_id=self.student.id, attendance_date=self.day,
            status="Absent", reason="Verified teacher correction", before_json="{}", actor_user_id=self.teacher.id,
            actor_name=self.teacher.full_name, actor_role=self.teacher.role))
        self.db.commit()
        row = self.student_row()
        self.assertEqual(row["status"], "Absent")
        self.assertEqual(row["source"], "Corrected by Teacher")
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)

    def test_legacy_time_out_correction_counts_attended_without_changing_audit(self):
        self.db.add(AttendanceCorrection(id="checkout-correction", person_id=self.student.id, attendance_date=self.day,
            status="Time Out", time_in=time(7, 30), time_out=time(16), reason="Verified checkout correction", before_json="{}",
            actor_user_id=self.admin.id, actor_name=self.admin.full_name, actor_role=self.admin.role))
        self.db.commit()
        self.assertEqual(self.student_row()["status"], "Present")
        self.assertEqual(self.db.get(AttendanceCorrection, "checkout-correction").status, "Time Out")

    def test_reset_supersedes_old_scan_but_new_scan_appears(self):
        self.scan(7, 30)
        reset_day(self.db, self.day, "Authorized isolated reset", self.admin)
        self.assertEqual(self.student_row()["status"], "No scan")
        self.scan(8)
        self.assertEqual(self.student_row()["status"], "Late")
        self.assertEqual(self.student_row()["time_in"], "08:00:00")
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 2)

    def test_batch_and_individual_views_agree_for_calendar_excuse_and_movement(self):
        self.scan(7, 30)
        self.db.add(CalendarException(id="holiday", event_date=self.day, event_type="Holiday", reason="School holiday", actor_user_id=self.admin.id, actor_name=self.admin.full_name))
        self.db.add(ExcusedAbsence(id="excuse", person_id=self.personnel.id, event_date=self.day, reason="Approved leave", actor_user_id=self.admin.id, actor_name=self.admin.full_name))
        self.db.commit()
        for person in (self.student, self.personnel):
            row = next(row for row in list_rows(self.db, self.day) if row["person_id"] == person.id)
            self.assertEqual(row, raw_row(self.db, person, self.day))
        self.student.enrollment_start_date = self.day + timedelta(days=1)
        self.db.commit()
        self.assertEqual(self.student_row()["status"], "Not Enrolled")

    def test_loading_query_count_is_constant_for_a_larger_roster(self):
        self.db.add_all([Person(external_id=f"EXTRA-{i}", full_name=f"Extra {i}", role="Student", sex="Female", grade="10", section="Rizal") for i in range(50)])
        self.db.commit()
        queries = []
        def count_query(_conn, _cursor, statement, *_args):
            queries.append(statement)
        event.listen(self.engine, "before_cursor_execute", count_query)
        try:
            rows = list_rows(self.db, self.day)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_query)
        self.assertEqual(len(rows), 52)
        self.assertLessEqual(len(queries), 8)

    def test_teacher_scope_excludes_other_classes_and_personnel(self):
        other = Person(external_id="OTHER", full_name="Other Student", role="Student", sex="Female", grade="7", section="Other")
        self.db.add(other)
        self.db.commit()
        rows = self.api_rows(self.teacher_headers)
        self.assertEqual([row["person_id"] for row in rows], [self.student.id])
        forbidden = self.client.get(f"/api/attendance?date={self.day}&grade=7&section=Other", headers=self.teacher_headers)
        self.assertEqual(forbidden.status_code, 403)

    def test_range_query_count_does_not_grow_with_the_roster(self):
        starts, ends = date(2026, 10, 1), date(2026, 10, 30)
        def export_queries():
            statements = []
            def count(_conn, _cursor, statement, *_args):
                statements.append(statement)
            event.listen(self.engine, "before_cursor_execute", count)
            try:
                rows = reports.attendance_range_rows(self.db, starts, ends, grade="10", section="Rizal")
            finally:
                event.remove(self.engine, "before_cursor_execute", count)
            return len(statements), len(rows)
        small = export_queries()
        self.db.add_all([Person(external_id=f"RANGE-{i}", full_name=f"Range Learner {i}", role="Student", sex="Female", grade="10", section="Rizal") for i in range(499)])
        self.db.commit()
        large = export_queries()
        self.assertEqual(small[1], 30)
        self.assertEqual(large[1], 15_000)
        self.assertEqual(small[0], large[0])
        self.assertLessEqual(large[0], 151)

    def test_sf2_pending_month_uses_batched_queries(self):
        from app.services.sf2 import sf2_pending_attendance
        self.student.enrollment_start_date = date(2026, 10, 1)
        self.db.commit()
        statements = []
        def count(_conn, _cursor, statement, *_args):
            statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", count)
        try:
            with patch('app.services.sf2.local_now', return_value=datetime(2026, 11, 1, tzinfo=MANILA)):
                result = sf2_pending_attendance(self.db, [self.student], 2026, 10)
        finally:
            event.remove(self.engine, "before_cursor_execute", count)
        self.assertEqual(result['unresolved_count'], 22)
        self.assertEqual(len(result['unresolved_examples']), 5)
        self.assertLessEqual(len(statements), 6, f'Monthly preview executed {len(statements)} queries')

    def test_range_rows_match_individual_rules_across_dates(self):
        starts, ends = self.day - timedelta(days=1), self.day + timedelta(days=5)
        self.student.enrollment_start_date = self.day
        self.student.enrollment_end_date = self.day + timedelta(days=3)
        self.personnel.assignment = "Science"
        reset_date = self.day + timedelta(days=1)
        reset = reset_day(self.db, reset_date, "Isolated report reset", self.admin)
        events = [
            AttendanceEvent(id="range-late-in", person_id=self.student.id, event_date=self.day, event_time=time(8), direction="Time In", status="Late", source="Test gate"),
            AttendanceEvent(id="range-late-out", person_id=self.student.id, event_date=self.day, event_time=time(16), direction="Time Out", status="Time Out", source="Test exit"),
            AttendanceEvent(id="range-pre-reset", person_id=self.student.id, event_date=reset_date, event_time=time(7), direction="Time In", status="Late", source="Old gate", created_at=reset.created_at - timedelta(seconds=1)),
            AttendanceEvent(id="range-post-reset", person_id=self.student.id, event_date=reset_date, event_time=time(8), direction="Time In", status="Present", source="New gate", created_at=reset.created_at + timedelta(seconds=1)),
        ]
        self.db.add_all(events + [
            CalendarException(id="range-holiday", event_date=reset_date, event_type="Holiday", reason="Test holiday", actor_user_id=self.admin.id, actor_name=self.admin.full_name),
            CalendarException(id="range-suspension", event_date=self.day + timedelta(days=2), event_type="Suspended", reason="Test suspension", actor_user_id=self.admin.id, actor_name=self.admin.full_name),
            ExcusedAbsence(id="range-excuse", person_id=self.personnel.id, event_date=reset_date, reason="Test leave", actor_user_id=self.admin.id, actor_name=self.admin.full_name),
            AttendanceCorrection(id="range-old-correction", person_id=self.student.id, attendance_date=reset_date, status="Absent", reason="Superseded test correction", before_json="{}", actor_user_id=self.admin.id, actor_name=self.admin.full_name, actor_role="admin", created_at=reset.created_at - timedelta(seconds=1)),
            AttendanceCorrection(id="range-correction", person_id=self.student.id, attendance_date=self.day + timedelta(days=2), status="Time Out", time_in=time(7), time_out=time(16), reason="Verified test correction", before_json="{}", actor_user_id=self.teacher.id, actor_name=self.teacher.full_name, actor_role="teacher"),
        ])
        self.db.commit()
        from app.services.attendance import active_people
        expected = []
        current = starts
        while current <= ends:
            for person in active_people(self.db):
                expected.append({**raw_row(self.db, person, current), "attendance_date": current})
            current += timedelta(days=1)
        rows = reports.attendance_range_rows(self.db, starts, ends)
        self.assertEqual(rows, expected)
        from app.services.attendance import rows_for_people_on_days
        days = [starts + timedelta(days=index) for index in range((ends - starts).days + 1)]
        batched = rows_for_people_on_days(self.db, active_people(self.db), days)
        self.assertEqual([{**row, 'attendance_date': day} for day, day_rows in batched.items()
                          for row in day_rows], expected)
        student_rows = {row["attendance_date"]: row for row in rows if row["person_id"] == self.student.id}
        self.assertEqual(student_rows[starts]["status"], "Not Enrolled")
        self.assertEqual(student_rows[self.day]["status"], "Late")
        self.assertEqual(student_rows[reset_date]["source"], "New gate")
        self.assertEqual(student_rows[self.day + timedelta(days=2)]["status"], "Present")
        self.assertEqual(student_rows[ends]["status"], "Enrollment Ended")

    def test_sf2_pending_preserves_calendar_and_registration_rules(self):
        from app.services.sf2 import sf2_pending_attendance, _school_days
        from app.services.attendance import is_instructional_day
        self.student.created_at = datetime(2026, 10, 5, 18)  # October 6 in Manila.
        self.student.enrollment_start_date = None
        self.db.add_all([
            CalendarException(id='sf2-holiday', event_date=date(2026, 10, 7), event_type='Holiday',
                              reason='Holiday', actor_user_id=self.admin.id, actor_name=self.admin.full_name),
            CalendarException(id='sf2-special', event_date=date(2026, 10, 8), event_type='Special Schedule',
                              reason='Special day', actor_user_id=self.admin.id, actor_name=self.admin.full_name),
            CalendarException(id='sf2-weekend', event_date=date(2026, 10, 10), event_type='Special Schedule',
                              reason='Weekend', actor_user_id=self.admin.id, actor_name=self.admin.full_name),
        ])
        self.db.commit()
        days = [date(2026, 10, day) for day in range(1, 32)]
        self.assertEqual(_school_days(self.db, 2026, 10),
                         [day for day in days if is_instructional_day(self.db, day)])
        with patch('app.services.sf2.local_now', return_value=datetime(2026, 10, 9, tzinfo=MANILA)):
            result = sf2_pending_attendance(self.db, [self.student], 2026, 10)
        self.assertEqual(result, {'unresolved_count': 2, 'unresolved_examples': [
            {'date': '2026-10-06', 'name': self.student.full_name},
            {'date': '2026-10-08', 'name': self.student.full_name},
        ]})

    def test_range_filters_and_identity_deduplication_are_preserved(self):
        duplicate = Person(external_id="student", full_name="ZZ Duplicate identity", role="Student", sex="Male", grade="10", section="Rizal")
        inactive = Person(external_id="INACTIVE", full_name="Inactive", role="Student", sex="Male", grade="10", section="Rizal", active=False)
        self.db.add_all([duplicate, inactive]); self.db.commit()
        for filters, ids in [
            ({"role": "Faculty"}, [self.personnel.id]),
            ({"grade": "10", "section": "Rizal"}, [self.student.id]),
            ({"person_id": self.student.id}, [self.student.id]),
            ({"role": "Faculty", "person_id": self.student.id}, []),
            ({"grade": "Unknown"}, []),
        ]:
            with self.subTest(filters=filters):
                rows = reports.attendance_range_rows(self.db, self.day, self.day, **filters)
                self.assertEqual([row["person_id"] for row in rows], ids)

    def test_range_validation_and_inclusive_limit_are_unchanged(self):
        from fastapi import HTTPException
        for starts, ends in [(self.day, self.day - timedelta(days=1)), (self.day, self.day + timedelta(days=367))]:
            with self.assertRaises(HTTPException) as error:
                reports.attendance_range_rows(self.db, starts, ends)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(reports.attendance_range_rows(self.db, self.day, self.day + timedelta(days=366), role="No matching role"), [])

    def test_personnel_export_includes_assignment_without_changing_attendance(self):
        from openpyxl import load_workbook
        self.personnel.assignment = "Science"
        self.db.commit()
        path = reports.generate_attendance_range_xlsx(self.db, self.day, self.day, role="Faculty")
        with path.open("rb") as stream:
            workbook = load_workbook(stream)
            self.assertEqual(workbook["Attendance Detail"]["F5"].value, "Science")
            workbook.close()
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])


if __name__ == "__main__":
    unittest.main()
