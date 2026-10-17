"""SMS enrollment integration without contacting a phone or school database."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

TEST_DIR = tempfile.TemporaryDirectory(prefix="eduscan-sms-tests-", dir=os.environ.get("EDUSCAN_TEST_TEMP_DIR"))
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EDUSCAN_DATA_DIR"] = TEST_DIR.name
os.environ["EDUSCAN_SECRET_KEY"] = "isolated-sms-enrollment-tests"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"
os.environ["SMS_GATEWAY_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import BiometricSample, Person, SmsOutbox, SystemSetting, User
from app.services import sms
from app.services.settings_store import get_json, get_secret, set_json, set_secret


class SmsEnrollmentTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = User(username="admin", role="admin", full_name="Admin", password_hash="unused", must_change_password=False)
        self.person = Person(external_id="TEST-1", full_name="Test Student", sex="Male", role="Student", guardian_phone="09171234567", biometric_consent=True)
        self.db.add_all([self.admin, self.person])
        self.db.commit()
        self.config = {"enabled": False, "gateway_url": "http://192.168.1.25:8080", "username": "test-gateway", "enrollment_notifications": True}
        set_json(self.db, "sms", self.config)
        set_secret(self.db, "sms.password", "test-only-password")
        def session_override():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = session_override
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_token(self.admin)}"}
        self.result = {"action": "created", "accepted": 20, "model": {"version": "test-model-1", "person_count": 1}}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def enroll(self, method="post", path=None):
        return getattr(self.client, method)(path or f"/api/biometrics/enrollments/{self.person.id}",
            headers=self.headers, data={"reason": "Authorized test enrollment"}, files=[("frames", ("test.jpg", b"synthetic-test-frame", "image/jpeg"))])

    def settings_payload(self, **changes):
        return {"enabled": True, "gateway_url": self.config["gateway_url"], "username": self.config["username"],
                "school_contact": "School office", **{f"{key}_template": value for key, value in sms.DEFAULT_TEMPLATES.items()},
                "enrollment_notifications": True, **changes}

    def record(self, status="queued", age=0):
        record = SmsOutbox(id=f"test-{len(self.db.scalars(select(SmsOutbox)).all())}", person_id=self.person.id,
            event_type="time_in", recipient="+639171234567", message="Test only", status=status,
            created_at=datetime.utcnow() - timedelta(days=age))
        self.db.add(record)
        self.db.commit()
        return record

    def test_successful_enrollment_queues_once_and_dispatches_only_that_notice(self):
        set_json(self.db, "sms", {**self.config, "enabled": True})
        with patch("app.main.biometric_service.enroll", return_value=self.result), patch("app.main.dispatch_record_by_id") as dispatch:
            first = self.enroll()
            second = self.enroll()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(first.json()["sms"]["dispatch_ready"])
        records = self.db.scalars(select(SmsOutbox)).all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].event_type, "enrollment")
        self.assertEqual(records[0].recipient, "+639171234567")
        self.assertIn("completed", records[0].message)
        self.assertEqual(dispatch.call_args.args, (records[0].id,))

    def test_disabled_gateway_queues_but_does_not_attempt_delivery(self):
        with patch("app.main.biometric_service.enroll", return_value=self.result), patch("app.main.dispatch_record_by_id") as dispatch:
            result = self.enroll()
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["sms"]["dispatch_ready"])
        self.assertIn("paused", result.json()["sms"]["message"])
        dispatch.assert_not_called()

    def test_reenrollment_and_legacy_endpoint_use_same_notification_flow(self):
        with patch("app.main.biometric_service.enroll", return_value={**self.result, "action": "updated"}) as enroll:
            result = self.enroll(method="put")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(enroll.call_args.kwargs["require_existing"])
        self.assertIn("updated", self.db.scalar(select(SmsOutbox)).message)
        with patch("app.main.biometric_service.enroll", return_value={**self.result, "model": {"version": "test-model-2"}}):
            legacy = self.enroll(path=f"/api/biometrics/enroll/{self.person.id}")
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(len(self.db.scalars(select(SmsOutbox)).all()), 2)

    def test_rejected_face_never_queues_notification(self):
        with patch("app.main.biometric_service.enroll", side_effect=HTTPException(409, detail="Duplicate face")), patch("app.main.dispatch_record_by_id") as dispatch:
            result = self.enroll()
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.db.scalars(select(SmsOutbox)).all(), [])
        dispatch.assert_not_called()

    def test_invalid_guardian_number_does_not_turn_saved_enrollment_into_failure(self):
        self.person.guardian_phone = "invalid"
        self.db.commit()
        def saved_enrollment(db, person, *_args, **_kwargs):
            db.add(BiometricSample(id="synthetic-sample", person_id=person.id, encrypted_path="test-only", sha256="test-only", quality_score=1))
            db.commit()
            return self.result
        with patch("app.main.biometric_service.enroll", side_effect=saved_enrollment):
            result = self.enroll()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["sms"]["status"], "not_queued")
        self.assertIsNotNone(self.db.get(BiometricSample, "synthetic-sample"))
        self.assertEqual(self.db.scalars(select(SmsOutbox)).all(), [])

    def test_missing_guardian_non_student_and_opt_out_do_not_queue(self):
        for changes in ({"guardian_phone": None}, {"role": "Faculty"}):
            original_phone, original_role = self.person.guardian_phone, self.person.role
            for key, value in changes.items():
                setattr(self.person, key, value)
            self.db.commit()
            self.assertEqual(sms.queue_enrollment_notice(self.db, self.person, self.result)["status"], "skipped")
            self.person.guardian_phone, self.person.role = original_phone, original_role
        set_json(self.db, "sms", {**self.config, "enrollment_notifications": False})
        self.assertEqual(sms.queue_enrollment_notice(self.db, self.person, self.result)["status"], "skipped")
        self.assertEqual(self.db.scalars(select(SmsOutbox)).all(), [])

    def test_enabling_requires_credentials_and_does_not_change_saved_settings_on_error(self):
        for changes in ({"username": ""}, {"password": ""}):
            response = self.client.put("/api/settings/sms", headers=self.headers, json=self.settings_payload(**changes))
            self.assertEqual(response.status_code, 422, response.text)
        self.db.expire_all()
        self.assertFalse(get_json(self.db, "sms", {})["enabled"])
        self.assertEqual(get_secret(self.db, "sms.password"), "test-only-password")

    def test_activation_holds_backlog_and_explicit_requeue_can_release_it(self):
        old = self.record(age=1)
        with patch("app.services.sms.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.25", 8080))]):
            enabled = self.client.put("/api/settings/sms", headers=self.headers, json=self.settings_payload())
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.assertEqual(enabled.json()["held_messages"], 1)
        self.db.expire_all()
        self.assertEqual(old.status, "held")
        with patch("app.services.sms.httpx.post") as post:
            sms.dispatch_queued(self.db)
            sms.send_record(self.db, old)
            post.assert_not_called()
        sms.requeue_record(self.db, old)
        with patch("app.services.sms.validate_local_gateway_url"), patch("app.services.sms.httpx.post") as post:
            post.return_value.content = b'{"id":"test-message"}'
            post.return_value.json.return_value = {"id": "test-message"}
            sms.send_record(self.db, old)
            post.assert_called_once()
        self.assertEqual(old.status, "accepted")
        encrypted = self.db.get(SystemSetting, "sms.password").encrypted_value
        self.assertNotIn(b"test-only-password", encrypted)

    def test_sender_does_not_send_again_when_already_accepted(self):
        accepted = self.record(status="accepted")
        with patch("app.services.sms.httpx.post") as post:
            sms.send_record(self.db, accepted)
            post.assert_not_called()

    def test_stale_queue_object_does_not_resend_an_accepted_message(self):
        record = self.record()
        with Session(self.engine) as other_sender:
            other_sender.get(SmsOutbox, record.id).status = "accepted"
            other_sender.commit()
        self.assertEqual(record.status, "queued")
        with patch("app.services.sms.httpx.post") as post:
            sms.send_record(self.db, record)
            post.assert_not_called()
        self.assertEqual(record.status, "accepted")

    def test_missing_credentials_do_not_attempt_send_or_consume_retries(self):
        set_json(self.db, "sms", {**self.config, "enabled": True, "username": ""})
        record = self.record()
        with patch("app.services.sms.httpx.post") as post:
            sms.send_record(self.db, record)
            post.assert_not_called()
        self.assertEqual(record.attempts, 0)
        self.assertEqual(record.status, "queued")

    def test_diagnostics_and_disabled_test_button_do_not_send(self):
        with patch("app.services.sms.validate_local_gateway_url", return_value=("192.168.1.25", 8080)), patch("app.services.sms.socket.create_connection"), patch("app.services.sms.httpx.get") as get, patch("app.services.sms.httpx.post") as post:
            get.return_value.status_code = 200
            diagnostic = self.client.get("/api/sms/gateway/check", headers=self.headers)
            response = self.client.post("/api/sms/test", headers=self.headers, data={"phone": "+639171234567"})
            post.assert_not_called()
        self.assertEqual(diagnostic.status_code, 200)
        self.assertTrue(diagnostic.json()["reachable"])
        self.assertFalse(diagnostic.json()["ready"])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.db.scalars(select(SmsOutbox)).all(), [])

    def test_read_only_gateway_check_reports_rejected_and_accepted_credentials(self):
        set_json(self.db, "sms", {**self.config, "enabled": True})
        with patch("app.services.sms.validate_local_gateway_url", return_value=("192.168.1.25", 8080)), patch("app.services.sms.socket.create_connection"), patch("app.services.sms.httpx.get") as get, patch("app.services.sms.httpx.post") as post:
            get.return_value.status_code = 401
            rejected = sms.gateway_diagnostics(self.db)
            self.assertFalse(rejected["ready"])
            self.assertFalse(rejected["credentials_accepted"])
            get.return_value.status_code = 200
            accepted = sms.gateway_diagnostics(self.db)
            self.assertTrue(accepted["ready"])
            self.assertTrue(accepted["credentials_accepted"])
            get.assert_called_with("http://192.168.1.25:8080/docs", auth=("test-gateway", "test-only-password"), timeout=4)
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
