"""New-person enrollment transactions; synthetic faces and temporary SQLite only."""
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_duplicate_enrollment as helpers
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import main
from app.auth import current_user
from app.database import Base, get_db
from app.models import AttendanceEvent, BiometricAuditEvent, GradeLevel, Person, SchoolSection, SmsOutbox, SystemAuditEvent


class AtomicEnrollmentTest(unittest.TestCase):
    def setUp(self):
        self.fixture = helpers.DuplicateEnrollmentTest()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.service = self.fixture.service
        grade = GradeLevel(name='7')
        self.db.add(grade)
        self.db.flush()
        self.db.add(SchoolSection(grade_level_id=grade.id, name='Jose'))
        self.db.commit()
        self.payload = {'external_id': 'NEW-STUDENT', 'surname': 'Example', 'first_name': 'New',
                        'sex': 'Male', 'role': 'Student', 'grade': '7', 'section': 'Jose', 'biometric_consent': True}
        self.overrides = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.fixture.admin
        self.service_patch = patch.object(main, 'biometric_service', self.service)
        self.service_patch.start()
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        self.service_patch.stop()
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.overrides)
        self.fixture.tearDown()

    def snapshot(self):
        return ({table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables},
                {path: path.read_bytes() for path in Path(self.fixture.directory.name).rglob('*.enc')})

    def enroll(self, faces=None, payload=None):
        faces = faces if faces is not None else helpers.face_set()
        with patch.object(self.service, 'process_frame', side_effect=faces):
            return self.client.post('/api/biometrics/register', data={'person': json.dumps(payload or self.payload)},
                                    files=[('frames', (f'{i}.jpg', b'synthetic', 'image/jpeg')) for i in range(len(faces))])

    def test_success_commits_person_samples_and_audits_together(self):
        before_attendance = self.db.scalars(select(AttendanceEvent)).all()
        result = self.enroll()
        self.assertEqual(result.status_code, 200, result.text)
        person = self.db.get(Person, result.json()['person_id'])
        self.assertEqual(person.full_name, 'Example, New')
        self.assertEqual(len(self.fixture.samples(person)), 15)
        self.assertIsNotNone(self.db.scalar(select(BiometricAuditEvent).where(BiometricAuditEvent.person_id == person.id)))
        self.assertIsNotNone(self.db.scalar(select(SystemAuditEvent).where(SystemAuditEvent.entity_id == str(person.id), SystemAuditEvent.entity_type == 'Person')))
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), before_attendance)

    def test_rejected_captures_leave_no_person_samples_audit_or_sms(self):
        before = self.snapshot()
        cases = [
            [replace(face, human_verified=False) for face in helpers.face_set()],
            helpers.face_set()[:5],
        ]
        with patch.object(main, 'queue_enrollment_notice') as notice, patch.object(main, 'dispatch_record_by_id') as dispatch:
            for faces in cases:
                result = self.enroll(faces)
                self.assertEqual(result.status_code, 422, result.text)
                self.assertEqual(self.snapshot(), before)
            notice.assert_not_called()
            dispatch.assert_not_called()

    def test_successful_new_student_keeps_existing_enrollment_sms_behavior(self):
        with patch.object(main, 'dispatch_record_by_id') as dispatch:
            result = self.enroll(payload={**self.payload, 'guardian_phone': '09171234567'})
        self.assertEqual(result.status_code, 200, result.text)
        notices = self.db.scalars(select(SmsOutbox)).all()
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].person_id, result.json()['person_id'])
        self.assertEqual(notices[0].event_type, 'enrollment')
        dispatch.assert_not_called()

    def test_sms_problem_does_not_report_successful_face_registration_as_failed(self):
        result = self.enroll(payload={**self.payload, 'guardian_phone': 'invalid'})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['sms']['status'], 'not_queued')
        self.assertEqual(len(self.fixture.samples(self.db.get(Person, result.json()['person_id']))), 15)

    def test_duplicate_face_preserves_all_existing_records_and_files(self):
        self.fixture.enroll(self.fixture.first, helpers.face_set())
        before = self.snapshot()
        result = self.enroll()
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(result.json()['detail']['code'], 'duplicate_face')
        self.assertEqual(self.snapshot(), before)

    def test_training_failure_rolls_back_new_person_and_samples(self):
        self.fixture.enroll(self.fixture.first, helpers.face_set())
        before = self.snapshot()
        with patch.object(self.service, 'train', side_effect=RuntimeError('Isolated training failure')):
            result = self.enroll(helpers.face_set(horizontal=True))
        self.assertEqual(result.status_code, 500)
        self.assertEqual(self.snapshot(), before)

    def test_commit_failure_restores_existing_model_and_removes_only_new_files(self):
        self.fixture.enroll(self.fixture.first, helpers.face_set())
        before = self.snapshot()
        with patch.object(self.db, 'commit', side_effect=RuntimeError('Isolated commit failure')):
            result = self.enroll(helpers.face_set(horizontal=True))
        self.assertEqual(result.status_code, 500)
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.service._recognizer)
        self.assertIsNone(self.service._model_path)

    def test_staff_assisted_registration_still_saves_without_face_capture(self):
        before_attendance = self.db.scalars(select(AttendanceEvent)).all()
        with patch.object(self.service, 'enroll') as face_enrollment:
            result = self.client.post('/api/persons', json={**self.payload, 'biometric_consent': False})
        self.assertEqual(result.status_code, 200, result.text)
        person = self.db.get(Person, result.json()['id'])
        self.assertFalse(person.biometric_consent)
        self.assertEqual(self.fixture.samples(person), [])
        face_enrollment.assert_not_called()
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), before_attendance)

    def test_duplicate_identifiers_and_missing_consent_do_not_save(self):
        self.fixture.first.lrn = '111111111111'
        self.db.commit()
        before = self.snapshot()
        for changes, status in [({'external_id': self.fixture.first.external_id}, 409),
                                ({'lrn': self.fixture.first.lrn}, 409),
                                ({'biometric_consent': False}, 422),
                                ({'section': 'Missing section'}, 422)]:
            result = self.enroll(payload={**self.payload, **changes})
            self.assertEqual(result.status_code, status, result.text)
            self.assertEqual(self.snapshot(), before)

    def test_invalid_payload_and_unauthorized_calls_do_not_save(self):
        before = self.snapshot()
        uploads = [('frames', ('test.jpg', b'synthetic', 'image/jpeg'))]
        for person in ('not-json', json.dumps({**self.payload, 'role': 'Invalid'})):
            result = self.client.post('/api/biometrics/register', data={'person': person}, files=uploads)
            self.assertEqual(result.status_code, 422, result.text)
            self.assertEqual(self.snapshot(), before)
        self.fixture.admin.role = 'teacher'
        self.db.commit()
        result = self.enroll()
        self.assertEqual(result.status_code, 403, result.text)
        self.assertIsNone(self.db.scalar(select(Person).where(Person.external_id == self.payload['external_id'])))


if __name__ == '__main__':
    unittest.main()
