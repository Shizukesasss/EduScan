from datetime import date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from pypdf import PdfReader
from PIL import Image
from io import BytesIO
import httpx
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

import test_attendance_sync as fixtures
from browser_test_client import issued_session_headers, response_session_headers
from app import main
from app.auth import hash_password
from app.database import Base
from app.models import AttendanceEvent, GeneratedReport, GradeLevel, Intervention, Person, SchoolSection, SchoolYear, SmsOutbox, StationSyncOperation, User
from app.rate_limits import RequestRateLimiter
from app.schemas import PersonCreate
from app.services import reports, sms, station_sync
from app.services.attendance import MANILA, record_gate_match
from app.services.audit import add_audit
from app.services.settings_store import set_json


class StationUpgradeTest(TestCase):
    def setUp(self):
        fixture = fixtures.AttendanceSyncTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.db, self.engine, self.client = fixture.db, fixture.engine, fixture.client
        self.admin, self.teacher, self.student, self.school_year = fixture.admin, fixture.teacher, fixture.student, fixture.school_year
        self.admin_headers, self.teacher_headers = fixture.admin_headers, fixture.teacher_headers
        self.day, self.scan = fixture.day, fixture.scan

    def student_payload(self):
        return {"external_id": "012345678901", "lrn": "012345678901", "surname": "Example", "first_name": "Lia",
                "sex": "Female", "date_of_birth": "2013-01-01", "role": "Student", "grade": "10", "section": "Rizal",
                "school_year_id": self.school_year.id, "enrollment_start_date": "2026-06-01",
                "biometric_consent": True}

    def test_notification_read_and_delete_are_private_to_the_account(self):
        now = datetime.utcnow()
        failed = SmsOutbox(id="failed-message", event_type="time_in", message="Test notice", recipient="test",
                           status="exhausted", created_at=now)
        officer = User(username="records", full_name="Records Officer", role="records_officer",
                       password_hash="unused", must_change_password=False)
        self.db.add_all([failed, officer])
        self.db.flush()
        officer_headers = issued_session_headers(self.db, officer)
        path = "/api/notifications"
        alert_path = path + "/sms-failed-message"
        self.assertEqual(self.client.get(path, headers=self.admin_headers).json()["unread"], 1)
        self.assertEqual(self.client.delete(alert_path, headers=self.teacher_headers).status_code, 404)
        self.assertEqual(self.client.patch(alert_path, headers=self.admin_headers).status_code, 204)
        read = self.client.get(path, headers=self.admin_headers).json()
        self.assertEqual(read["unread"], 0)
        self.assertTrue(read["items"][0]["read"])
        self.assertEqual(self.client.get(path, headers=officer_headers).json()["unread"], 1)
        self.assertEqual(self.client.delete(alert_path, headers=self.admin_headers).status_code, 204)
        self.assertEqual(self.client.patch(alert_path, headers=self.admin_headers).status_code, 204)
        self.assertEqual(self.client.get(path, headers=self.admin_headers).json(), {"items": [], "unread": 0})
        self.assertEqual(self.db.get(SmsOutbox, failed.id).status, "exhausted")
        self.db.add(SmsOutbox(id="new-failure", event_type="time_out", message="More test data", recipient="test",
                              status="failed", created_at=now + timedelta(seconds=1)))
        self.db.commit()
        recent = self.client.get(path, headers=self.admin_headers).json()
        self.assertEqual([item["id"] for item in recent["items"]], ["sms-new-failure"])
        self.assertEqual(recent["unread"], 1)

    def test_user_can_save_and_remove_their_profile_picture_and_display_name(self):
        path = "/api/account/profile"
        before = self.client.get("/api/auth/me", headers=self.admin_headers).json()
        self.assertEqual(before["display_name"], self.admin.full_name)
        self.assertIsNone(before["profile_photo_revision"])
        self.assertEqual(self.client.get(path + "/photo").status_code, 401)

        image = BytesIO()
        Image.new("RGBA", (700, 400), (80, 140, 215, 80)).save(image, format="PNG")
        saved = self.client.patch(path, headers=self.admin_headers, data={"display_name": "  María Santos  "},
                                  files={"picture": ("portrait.png", image.getvalue(), "image/png")})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["display_name"], "María Santos")
        self.assertTrue(saved.json()["profile_photo_revision"])
        self.db.refresh(self.admin)
        self.assertEqual(self.admin.full_name, before["full_name"])
        self.assertEqual(self.admin.role, "admin")

        other = self.client.get(path + "/photo", headers=self.teacher_headers)
        self.assertEqual(other.status_code, 404)
        new_session = issued_session_headers(self.db, self.admin)
        profile = self.client.get("/api/auth/me", headers=new_session).json()
        self.assertEqual(profile["display_name"], "María Santos")
        self.assertEqual(profile["profile_photo_revision"], saved.json()["profile_photo_revision"])
        picture = self.client.get(path + "/photo", headers=new_session)
        self.assertEqual(picture.status_code, 200)
        self.assertEqual(picture.headers["content-type"], "image/jpeg")
        self.assertIn("no-store", picture.headers["cache-control"])
        with Image.open(BytesIO(picture.content)) as avatar:
            self.assertEqual((avatar.format, avatar.size, avatar.mode), ("JPEG", (384, 384), "RGB"))

        removed = self.client.patch(path, headers=new_session, data={"remove_picture": "true"})
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertIsNone(removed.json()["profile_photo_revision"])
        self.assertEqual(removed.json()["display_name"], "María Santos")
        self.assertEqual(self.client.get(path + "/photo", headers=new_session).status_code, 404)

    def test_invalid_profile_upload_does_not_save_other_changes(self):
        path = "/api/account/profile"
        for name, content, expected in (
            ("fake.png", b"<svg></svg>", 422),
            ("large.png", b"x" * (5 * 1024 * 1024 + 1), 413),
        ):
            result = self.client.patch(path, headers=self.admin_headers, data={"display_name": "Temporary profile"},
                                       files={"picture": (name, content, "image/png")})
            self.assertEqual(result.status_code, expected)
        result = self.client.patch(path, headers=self.admin_headers, data={"display_name": "   "})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.admin_headers).json()["display_name"], self.admin.full_name)

    def test_admin_can_replace_sign_in_email_and_password_from_account_security(self):
        old_password, new_password = "Previous-Test-Pass1!", "Updated-Test-Pass2!"
        self.admin.password_hash = hash_password(old_password)
        self.db.commit()
        headers = issued_session_headers(self.db, self.admin)
        credentials = {"email": "Admin@example.org", "current_password": old_password, "new_password": new_password}
        endpoint = "/api/account/credentials"
        self.assertEqual(self.client.put(endpoint, headers=headers,
                                        json={**credentials, "current_password": "wrong"}).status_code, 422)
        self.assertEqual(self.client.put(endpoint, headers=headers, json=credentials).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        for identifier, password in (("admin", old_password), ("admin", new_password), ("admin@example.org", old_password)):
            self.assertEqual(self.client.post("/api/auth/login", json={"username": identifier, "password": password}).status_code, 401)
        login = self.client.post("/api/auth/login", json={"username": "ADMIN@example.org", "password": new_password})
        self.assertEqual(login.status_code, 200, login.text)
        signed_in = response_session_headers(login)
        path = "/api/account/profile"
        self.assertEqual(self.client.get(path, headers=signed_in).json()["email"], "admin@example.org")
        response = self.client.put(path, headers=signed_in, data={
            "display_name": "Local Admin", "email": "unapproved@example.org", "phone_number": "+63 917 123 4567",
            "emergency_name": "Emergency Test", "emergency_phone": "(02) 8123-4567",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email"], "admin@example.org")
        self.assertEqual(self.client.get(path, headers=signed_in).json()["phone_number"], "+63 917 123 4567")
        self.assertEqual(self.client.get(path, headers=signed_in).json()["emergency_phone"], "(02) 8123-4567")
        self.assertNotIn("emergency_phone", self.client.get("/api/auth/me", headers=signed_in).json())
        self.assertEqual(self.client.get(path, headers=self.teacher_headers).json()["emergency_phone"], "")
        self.assertEqual(self.client.put(path, headers=signed_in, data={"display_name": "Local Admin"}).status_code, 200)
        self.assertEqual(self.client.get(path, headers=signed_in).json()["emergency_phone"], "")

    def test_email_change_requires_approval_for_the_exact_address(self):
        old_password, new_password = "Previous-Test-Pass1!", "Updated-Test-Pass2!"
        self.teacher.password_hash = hash_password(old_password)
        self.db.commit()
        headers = issued_session_headers(self.db, self.teacher)
        endpoint = "/api/account/credentials"
        credentials = {"email": "teacher@example.org", "current_password": old_password, "new_password": new_password}
        self.assertEqual(self.client.put("/api/account/profile", data={"display_name": "Teacher"}, headers=headers).status_code, 422)
        self.assertEqual(self.client.put(endpoint, json=credentials, headers=headers).status_code, 403)
        requested = self.client.post("/api/account/email-change", json={"email": credentials["email"]}, headers=headers)
        self.assertEqual(requested.status_code, 200, requested.text)
        self.assertEqual(requested.json()["status"], "pending")
        queue = "/api/admin/email-change-requests"
        self.assertEqual(self.client.get(queue, headers=headers).status_code, 403)
        self.assertEqual(self.client.get(queue, headers=self.admin_headers).json()[0]["id"], requested.json()["id"])
        review = {"request_id": requested.json()["id"], "approve": True}
        approval = self.client.post(f"{queue}/{self.teacher.id}", json=review, headers=self.admin_headers)
        self.assertEqual(approval.status_code, 200, approval.text)
        self.assertEqual(self.client.put(endpoint, json={**credentials, "email": "different@example.org"}, headers=headers).status_code, 403)
        self.assertEqual(self.client.put(endpoint, json=credentials, headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        login = self.client.post("/api/auth/login", json={"username": credentials["email"], "password": new_password})
        self.assertEqual(login.status_code, 200, login.text)
        current = self.client.get("/api/account/email-change", headers=response_session_headers(login)).json()
        self.assertEqual(current, {"email": credentials["email"], "request": None})

    def test_lrn_validation_and_leading_zero(self):
        for lrn in (None, "１２３４５６７８９０１２", "01234567890a", " 012345678901", "01234567890"):
            response = self.client.post("/api/persons", json={**self.student_payload(), "lrn": lrn},
                                        headers=self.admin_headers)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"]["code"], "invalid_lrn")
        response = self.client.post("/api/persons", json=self.student_payload(), headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["lrn"], "012345678901")

    def test_auth_log_pdf_and_verification_are_admin_only(self):
        self.admin.password_hash = hash_password("TestRolePassword!2026")
        self.db.commit()
        path = "/api/admin/authentication-log"
        for password, expected in (("wrong", 401), ("TestRolePassword!2026", 200)):
            result = self.client.post("/api/auth/login", json={"username": "admin", "password": password})
            self.assertEqual(result.status_code, expected, result.text)
        self.admin_headers = response_session_headers(result)
        self.assertEqual(self.client.get(path, headers=self.teacher_headers).status_code, 403)
        attempts = self.client.get(path, headers=self.admin_headers).json()
        self.assertEqual([row["outcome"] for row in attempts], ["Succeeded", "Failed"])
        with patch.object(reports, "REPORT_DIR", Path(fixtures.TEST_DIR.name)), \
             patch.object(main, "EXPORT_DIR", Path(fixtures.TEST_DIR.name)):
            exported = self.client.get(path + ".pdf", headers=self.admin_headers)
            self.assertEqual(exported.status_code, 200, exported.text if exported.status_code != 200 else "")
            content = PdfReader(BytesIO(exported.content)).pages[0].extract_text()
            self.assertIn("Authentication Log", content)
            self.assertNotIn("System Generated", content)
            history = self.client.get("/api/reports/history", headers=self.admin_headers).json()
            entry = next(item for item in history if item["report_type"] == main.AUTH_LOG_REPORT)
            self.assertEqual(entry["sha256"], sha256(exported.content).hexdigest())
            href = f"/api/reports/history/{entry['id']}"
            self.assertEqual(self.client.get(href + "/download", headers=self.admin_headers).content, exported.content)
            with Session(self.db.get_bind()) as report_db:
                saved = report_db.get(GeneratedReport, entry["id"])
                saved.file_path = fr"Z:\prior-host\exports\registered\{entry['id']}.pdf"
                report_db.commit()
            self.assertEqual(self.client.get(href + "/download", headers=self.admin_headers).content, exported.content)
            for data, outcome in ((exported.content, "match"), (exported.content + b"\n%changed", "differs")):
                uploaded = {"file": ("copy.pdf", data, "application/pdf")}
                self.assertEqual(self.client.post(href + "/verify", files=uploaded, headers=self.admin_headers).json(), {
                    "status": outcome,
                    "original_sha256": entry["sha256"],
                    "submitted_sha256": sha256(data).hexdigest(),
                })
                self.assertIn(self.client.post(href + "/verify", files=uploaded, headers=self.teacher_headers).status_code, (403, 404))
            second = self.client.get(path + ".pdf?account=99999", headers=self.admin_headers)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(self.client.post(href + "/verify", headers=self.admin_headers,
                                               files={"file": ("other.pdf", second.content, "application/pdf")}).json()["status"], "differs")

    def test_auth_log_includes_saved_legacy_sign_ins_with_philippine_date_filters(self):
        start_utc = datetime(2026, 10, 31, 16)
        self.admin.last_login_at = start_utc + timedelta(minutes=1)
        self.teacher.last_login_at = start_utc
        audit = add_audit(self.db, self.admin, "Succeeded", "Authentication", self.admin.id, "Sign-in succeeded",
                          after={"account": self.admin.username, "method": "password", "source": "127.0.0.1"})
        audit.created_at = self.admin.last_login_at
        self.db.commit()
        path = "/api/admin/authentication-log"
        filters = {"starts_on": "2026-11-01", "ends_on": "2026-11-01"}
        response = self.client.get(path, params=filters, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        self.assertEqual([row["account"] for row in rows], [self.admin.username, self.teacher.username])
        self.assertEqual(rows[1]["time"], start_utc.isoformat() + "Z")
        self.assertIsNone(rows[1]["source"])
        self.assertEqual(rows[1]["method"], "Unknown (historical)")
        account = {**filters, "account": self.teacher.id}
        self.assertEqual(self.client.get(path, params=account, headers=self.admin_headers).json(), [rows[1]])
        self.assertEqual(self.client.get(path, params={"ends_on": "2026-10-31"}, headers=self.admin_headers).json(), [])
        with patch.object(reports, "REPORT_DIR", Path(fixtures.TEST_DIR.name)), \
             patch.object(main, "EXPORT_DIR", Path(fixtures.TEST_DIR.name)):
            pdf = self.client.get(path + ".pdf", params=account, headers=self.admin_headers)
            self.assertEqual(pdf.status_code, 200)
            pdf_text = PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
            self.assertIn(self.teacher.username, pdf_text)
            self.assertIn("Unknown (historical)", " ".join(pdf_text.split()))

    def test_unified_activity_filters_and_saved_pdf_permissions(self):
        limiter = main.app.state.request_limiter
        self.addCleanup(setattr, main.app.state, "request_limiter", limiter)
        main.app.state.request_limiter = RequestRateLimiter(limiter.policies)
        path = "/api/admin/activity"
        starts_on = "2026-11-01"
        at_midnight = datetime(2026, 10, 31, 16)
        self.teacher.last_login_at = at_midnight
        self.admin.last_login_at = at_midnight + timedelta(minutes=1)
        signed_in = add_audit(self.db, self.admin, "Succeeded", "Authentication", self.admin.id, "Sign-in succeeded",
                              after={"account": self.admin.username, "source": "192.0.2.18", "method": "password"})
        signed_in.created_at = self.admin.last_login_at
        rejected = add_audit(self.db, None, "Failed", "Authentication", None, "Sign-in failed",
                             after={"source": "192.0.2.18", "method": "password"})
        rejected.created_at = at_midnight + timedelta(minutes=2)
        edited = add_audit(self.db, self.admin, "Update", "Person", self.student.id, "Learner record updated",
                           after={"date_of_birth": "2013-03-02", "active": True})
        edited.created_at = at_midnight + timedelta(minutes=3)
        self.db.commit()
        officers = []
        for role in ("records_officer", "privacy_officer"):
            user = User(username=role, full_name=role, role=role, password_hash="unused", must_change_password=False)
            self.db.add(user)
            self.db.flush()
            officers.append(issued_session_headers(self.db, user))
        dates = {"starts_on": starts_on, "ends_on": starts_on}
        feed = self.client.get(path, params=dates, headers=self.admin_headers)
        self.assertEqual(feed.status_code, 200, feed.text)
        history = feed.json()["rows"]
        self.assertEqual([row["action"] for row in history], ["Update", "Failed", "Succeeded", "Succeeded"])
        self.assertEqual(history[-1]["summary"], "Last known sign-in")
        self.assertIsNone(history[-1]["method"])
        self.assertEqual(self.client.get(path, params={**dates, "kind": "sign-ins", "outcome": "Failed"},
                                         headers=self.admin_headers).json()["rows"], [history[1]])
        self.assertEqual(self.client.get(path, params={**dates, "kind": "sign-ins", "account": self.admin.id},
                                         headers=self.admin_headers).json()["rows"], [history[2]])
        self.assertEqual(self.client.get(path, params={**dates, "kind": "changes", "action": "update", "entity": "person",
                                                      "actor": "admin"}, headers=self.admin_headers).json()["rows"], [history[0]])
        for headers in officers:
            visible = self.client.get(path, params=dates, headers=headers).json()["rows"]
            self.assertEqual(len(visible), 1)
            self.assertEqual(visible[0]["after"], {"active": True})
            self.assertEqual(self.client.get(path, params={"kind": "sign-ins"}, headers=headers).status_code, 403)
        self.assertEqual(self.client.get(path, headers=self.teacher_headers).status_code, 403)

        with patch.object(reports, "REPORT_DIR", Path(fixtures.TEST_DIR.name)), \
             patch.object(main, "EXPORT_DIR", Path(fixtures.TEST_DIR.name)):
            admin_pdf = self.client.get(path + ".pdf", params=dates, headers=self.admin_headers)
            self.assertEqual(admin_pdf.status_code, 200, admin_pdf.text if admin_pdf.status_code != 200 else "")
            contents = " ".join(PdfReader(BytesIO(admin_pdf.content)).pages[0].extract_text().split())
            self.assertIn("Time (PHT)", contents)
            self.assertIn("2026-11-01 00:00:00", contents)
            self.assertIn("Starts on: 2026-11-01", contents)
            self.assertIn("Learner record updated", contents)
            self.assertIn("192.0.2.18", contents)
            self.assertNotIn("System Generated", contents)
            saved = self.client.get(path + "/reports", headers=self.admin_headers).json()[0]
            self.assertEqual(saved["sha256"], sha256(admin_pdf.content).hexdigest())
            saved_path = f"/api/reports/history/{saved['id']}"
            self.assertEqual(self.client.get(saved_path + "/download", headers=self.admin_headers).content, admin_pdf.content)
            for headers in officers:
                self.assertNotIn(saved["id"], [item["id"] for item in self.client.get("/api/reports/history", headers=headers).json()])
                self.assertEqual(self.client.get(saved_path + "/download", headers=headers).status_code, 404)
                self.assertEqual(self.client.post(saved_path + "/verify", headers=headers,
                                                  files={"file": ("test.pdf", admin_pdf.content)}).status_code, 404)
                self.assertEqual(self.client.get(path + ".pdf", params={"kind": "sign-ins"}, headers=headers).status_code, 403)
            for headers in officers:
                visible_pdf = self.client.get(path + ".pdf", params=dates, headers=headers)
                self.assertEqual(visible_pdf.status_code, 200)
                text = PdfReader(BytesIO(visible_pdf.content)).pages[0].extract_text()
                self.assertNotIn("192.0.2.18", text)
                saved = self.client.get(path + "/reports", headers=headers).json()[0]
                downloadable = f"/api/reports/history/{saved['id']}"
                self.assertEqual(self.client.get(downloadable + "/download", headers=headers).content, visible_pdf.content)
                self.assertEqual(self.client.post(downloadable + "/verify", headers=headers,
                                                  files={"file": ("test.pdf", visible_pdf.content)}).json()["status"], "match")

    def test_gate_order_sms_and_network_rejection(self):
        self.student.guardian_phone = "+639171234567"
        self.db.commit()
        last = self.scan(9, 30)
        first = self.scan(7, 30)
        rows = self.client.get(f"/api/gate/recent?date={self.day}", headers=self.admin_headers).json()
        self.assertEqual([row["id"] for row in rows], [last["id"], first["id"]])
        self.assertEqual(rows[0]["sms_status"], "queued")
        self.assertEqual(rows[0]["sms_id"], last["sms_id"])
        saved = self.client.put("/api/settings/gate-network", headers=self.admin_headers,
                                json={"restricted": True, "allowed_networks": ["10.50.0.0/24"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        response = self.client.post("/api/biometrics/recognize-many", files={"frame": ("frame.jpg", b"dummy")},
                                    headers={**self.admin_headers, "X-Forwarded-For": "10.50.0.15"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "gate_network_denied")

    def test_roster_loading_uses_one_select(self):
        selections = []
        def observe(_connection, _cursor, statement, *_):
            if statement.lstrip().upper().startswith("SELECT"):
                selections.append(statement)
        event.listen(self.engine, "before_cursor_execute", observe)
        try:
            rows = main.admin_persons(db=self.db, _=self.admin)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(selections), 1)
        finally:
            event.remove(self.engine, "before_cursor_execute", observe)

    def test_interventions_batch_queries_and_respect_prior_advisory_assignments(self):
        class ReportingDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 6, 4)

        self.db.add(SchoolYear(name="2025-2026", starts_on=date(2025, 6, 1), ends_on=date(2026, 5, 31), active=True))
        for day in (date(2026, 5, 29), date(2026, 6, 1)):
            self.db.add(AttendanceEvent(id=day.isoformat(), person_id=self.student.id, event_date=day,
                                        event_time=time(15), direction="Daily Close", status="Absent"))
        for clock in (datetime(2026, 6, 1), datetime(2026, 6, 2)):
            self.db.add(Intervention(id=clock.isoformat(), person_id=self.student.id, intervention_type="Follow-up",
                                     note="Synthetic follow-up", actor_user_id=self.teacher.id,
                                     actor_name=self.teacher.full_name, created_at=clock))
        self.db.commit()
        statements = []
        def observe(_connection, _cursor, statement, *_):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", observe)
        try:
            with patch.object(main, "date", ReportingDate):
                as_teacher = main.interventions(days=90, threshold=1, db=self.db, user=self.teacher)
                self.assertLessEqual(len(statements), 10)
                as_admin = main.interventions(days=90, threshold=1, db=self.db, user=self.admin)
            self.assertEqual([row["absence_count"] for row in as_teacher], [1])
            self.assertEqual([row["absence_count"] for row in as_admin], [2])
            self.assertEqual(as_teacher[0]["last_absence"], ReportingDate.today() - timedelta(days=3))
            self.assertEqual([row["id"] for row in as_teacher[0]["logs"]], ["2026-06-02T00:00:00", "2026-06-01T00:00:00"])
        finally:
            event.remove(self.engine, "before_cursor_execute", observe)

    def test_sms_retry_reuses_gateway_id_after_lost_response(self):
        self.student.guardian_phone = "+639171234567"
        self.db.commit()
        gate = self.scan(7, 30)
        notice = self.db.get(SmsOutbox, gate["sms_id"])
        config = {"enabled": True, "gateway_url": "http://192.168.1.100:8080", "username": "test", "password": "test"}
        with patch.object(sms, "sms_config", return_value=config), \
             patch.object(sms, "validate_local_gateway_url"), \
             patch.object(sms, "_gateway_state", return_value={"id": notice.id, "state": "Pending"}) as lookup, \
             patch.object(sms.httpx, "post", side_effect=[httpx.ReadTimeout("synthetic timeout"), httpx.Response(409)]) as dispatch:
            self.assertEqual(sms.send_record(self.db, notice).status, "failed")
            sms.requeue_record(self.db, notice)
            self.assertEqual(sms.send_record(self.db, notice).status, "accepted")
        self.assertEqual([request.kwargs["json"]["id"] for request in dispatch.call_args_list], [notice.id, notice.id])
        lookup.assert_called_once_with(config, notice.id)

    def test_offline_enrollment_and_punch_retry_after_remote_commit(self):
        remote_engine = create_engine("sqlite://")
        Base.metadata.create_all(remote_engine)
        try:
            with Session(remote_engine) as remote, patch.object(station_sync, "enabled", True):
                remote.add_all([
                    User(username=self.admin.username, full_name="School admin", role="admin", password_hash="unused"),
                    SchoolYear(name=self.school_year.name, starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31)),
                    GradeLevel(id=90, name="10"),
                ])
                remote.flush()
                remote.add(SchoolSection(name="Rizal", grade_level_id=90))
                remote.commit()
                payload = self.student_payload()
                payload["guardian_phone"] = "+639171234567"
                person = main._new_person_record(PersonCreate.model_validate(payload), self.db, self.admin)
                self.db.commit()
                gate = record_gate_match(self.db, person, None, datetime.combine(self.day, time(7, 30), MANILA),
                                         sync_actor=self.admin, station_id="synthetic-station")
                self.assertTrue(gate["pending_sync"])
                self.assertFalse(self.db.scalars(select(SmsOutbox)).all())
                operation = self.db.get(StationSyncOperation, gate["id"])
                self.assertNotIn(payload["lrn"].encode(), operation.payload)
                set_json(self.db, station_sync.policy_key, "unrestricted")
                # A disconnected destination leaves both operations pending.
                with patch.object(station_sync, "_apply", side_effect=ConnectionError("synthetic disconnect")):
                    with self.assertRaises(ConnectionError):
                        station_sync.sync_pending(self.db, remote, main._new_person_record)
                self.assertEqual(station_sync.status(self.db)["pending"], 2)
                # Commit the destination writes while leaving local acknowledgments pending.
                for row in self.db.scalars(select(StationSyncOperation).order_by(StationSyncOperation.created_at)).all():
                    station_sync._apply(remote, row, main._new_person_record)
                with Session(self.engine) as reopened:
                    station_sync.sync_pending(reopened, remote, main._new_person_record)
                    self.assertEqual(station_sync.status(reopened)["synced"], 2)
                self.assertEqual(len(remote.scalars(select(Person)).all()), 1)
                self.assertEqual(len(remote.scalars(select(SmsOutbox)).all()), 1)
                self.assertEqual(remote.get(AttendanceEvent, gate["id"]).event_time, time(7, 30))
                conflict_payload = {**payload, "lrn": "222345678901", "external_id": "222345678901"}
                remote.add(Person(lrn=conflict_payload["lrn"], external_id=conflict_payload["external_id"],
                                  full_name="Conflicting school record", sex="Female", role="Student", biometric_consent=True))
                remote.commit()
                conflicting_person = main._new_person_record(PersonCreate.model_validate(conflict_payload), self.db, self.admin)
                self.db.commit()
                conflicted_gate = record_gate_match(self.db, conflicting_person, None,
                    datetime.combine(self.day, time(8, 30), MANILA), sync_actor=self.admin, station_id="synthetic-station")
                station_sync.sync_pending(self.db, remote, main._new_person_record)
                self.assertEqual(station_sync.status(self.db)["conflict"], 2)
                self.assertIsNone(remote.get(AttendanceEvent, conflicted_gate["id"]))

                revoked_payload = {**payload, "lrn": "322345678901", "external_id": "322345678901"}
                revoked_person = main._new_person_record(PersonCreate.model_validate(revoked_payload), self.db, self.admin)
                self.db.commit()
                revoked_person.biometric_consent = False
                self.db.commit()
                station_sync.sync_pending(self.db, remote, main._new_person_record)
                self.assertEqual(station_sync.status(self.db)["conflict"], 3)
                self.assertIsNone(remote.scalar(select(Person).where(Person.lrn == revoked_payload["lrn"])))
        finally:
            remote_engine.dispose()
