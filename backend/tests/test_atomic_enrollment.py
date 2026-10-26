"""New-person enrollment transactions; synthetic faces and temporary SQLite only."""
import json
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

import test_duplicate_enrollment as helpers
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import main
from app.auth import current_user
from app.database import Base, get_db
from app.models import AttendanceEvent, BiometricAuditEvent, GradeLevel, LearnerEnrollment, Person, SchoolSection, SchoolYear, SmsOutbox, SystemAuditEvent


class AtomicEnrollmentTest(unittest.TestCase):
    def test_student_can_register_with_only_lrn_and_keep_legacy_id_on_edit(self):
        payload = {**self.payload, 'lrn': '123456789012'}
        payload.pop('external_id')
        response = self.client.post('/api/persons', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['external_id'], payload['lrn'])
        self.assertEqual(response.json()['lrn'], payload['lrn'])
        self.assertEqual(self.client.post('/api/persons', json=payload).status_code, 409)
        update = {**self.payload, 'external_id': self.fixture.first.external_id, 'lrn': '234567890123'}
        response = self.client.patch(f'/api/persons/{self.fixture.first.id}', json=update)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['external_id'], self.fixture.first.external_id)
        self.assertEqual(self.db.scalar(select(LearnerEnrollment).where(
            LearnerEnrollment.person_id == self.fixture.first.id)).school_year_id, self.school_year.id)

    def test_new_student_requires_school_year_and_enrollment_start_date(self):
        for field in ('school_year_id', 'enrollment_start_date'):
            payload = {**self.payload, 'external_id': f'MISSING-{field}'}
            payload.pop(field)
            response = self.client.post('/api/persons', json=payload)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIsNone(self.db.scalar(select(Person).where(Person.external_id == payload['external_id'])))
            self.assertIsNone(self.db.scalar(select(LearnerEnrollment)))

    def test_new_student_rejects_enrollment_start_outside_school_year(self):
        response = self.client.post('/api/persons', json={**self.payload,
            'external_id': 'OUTSIDE-YEAR', 'enrollment_start_date': '2027-04-01'})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(self.db.scalar(select(Person).where(Person.external_id == 'OUTSIDE-YEAR')))
        self.assertIsNone(self.db.scalar(select(LearnerEnrollment)))

    def test_staff_requires_employee_id_and_preserves_phone(self):
        for role in ('Faculty', 'Non-teaching Personnel'):
            payload = {**self.payload, 'role': role, 'external_id': f'EMP-{role}', 'guardian_phone': '+639123456789'}
            response = self.client.post('/api/persons', json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['guardian_phone'], payload['guardian_phone'])
            payload.pop('external_id')
            self.assertEqual(self.client.post('/api/persons', json=payload).status_code, 422)

    def _dispose_role(self, role):
        self.fixture.first.role = role
        self.fixture.first.lrn = '123456789012' if role == 'Student' else None
        self.db.commit()
        self.fixture.enroll(self.fixture.first, helpers.face_set())
        self.fixture.enroll(self.fixture.second, helpers.face_set(horizontal=True))
        samples, _ = self.service._identity_gallery(self.db)
        deleted_id = self.fixture.first.id
        deleted_paths = [Path(sample.encrypted_path) for sample in samples if sample.person_id == deleted_id]
        other_paths = [Path(sample.encrypted_path) for sample in samples if sample.person_id != deleted_id]
        identifier = self.fixture.first.lrn or self.fixture.first.external_id
        with patch('app.services.disposal.biometric_service', self.service):
            response = self.client.request('DELETE', f'/api/admin/persons/{deleted_id}/records',
                                           json={'confirmed': True, 'confirmation': identifier})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['removed_counts']['face_samples'], 15)
        self.assertEqual(response.json()['file_cleanup_pending'], 0)
        self.assertIsNone(self.db.get(Person, deleted_id))
        self.assertTrue(all(not path.exists() for path in deleted_paths))
        self.assertTrue(all(path.exists() for path in other_paths))
        self.assertFalse(any(key[1] == deleted_id for key in self.service._identity_cache))
        remaining, _ = self.service._identity_gallery(self.db)
        self.assertEqual({sample.person_id for sample in remaining}, {self.fixture.second.id})

    def test_dispose_student_removes_face_files_and_identity(self):
        self._dispose_role('Student')

    def test_dispose_teacher_removes_face_files_and_identity(self):
        self._dispose_role('Faculty')

    def test_dispose_non_teaching_staff_removes_face_files_and_identity(self):
        self._dispose_role('Non-teaching Personnel')

    def test_disposal_requires_checkbox_identifier_and_admin(self):
        url = f'/api/admin/persons/{self.fixture.first.id}/records'
        for payload in ({'confirmation': self.fixture.first.external_id}, {'confirmed': False, 'confirmation': self.fixture.first.external_id},
                        {'confirmed': True, 'confirmation': 'WRONG-ID'}):
            self.assertEqual(self.client.request('DELETE', url, json=payload).status_code, 422)
            self.assertIsNotNone(self.db.get(Person, self.fixture.first.id))
        self.fixture.admin.role = 'teacher'
        self.assertEqual(self.client.request('DELETE', url, json={'confirmed': True, 'confirmation': self.fixture.first.external_id}).status_code, 403)

    def setUp(self):
        self.fixture = helpers.DuplicateEnrollmentTest()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.service = self.fixture.service
        grade = GradeLevel(name='7')
        self.db.add(grade)
        self.db.flush()
        section = SchoolSection(grade_level_id=grade.id, name='Jose')
        self.school_year = SchoolYear(name='2026-2027', starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
        self.db.add_all([section, self.school_year])
        self.db.commit()
        self.section = section
        self.payload = {'external_id': 'NEW-STUDENT', 'surname': 'Example', 'first_name': 'New',
                        'sex': 'Male', 'date_of_birth': '2012-01-01', 'role': 'Student', 'grade': '7', 'section': 'Jose', 'biometric_consent': True,
                        'school_year_id': self.school_year.id, 'enrollment_start_date': '2026-06-01'}
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
        placement = self.db.scalar(select(LearnerEnrollment).where(LearnerEnrollment.person_id == person.id))
        self.assertEqual((placement.school_year_id, placement.grade_level_id, placement.section_id, placement.starts_on),
                         (self.school_year.id, self.section.grade_level_id, self.section.id, date(2026, 6, 1)))
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
                self.assertEqual(self.db.scalars(select(LearnerEnrollment)).all(), [])
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
        from fastapi import HTTPException
        from app.services import sms
        with patch.object(sms, 'normalize_phone', side_effect=HTTPException(status_code=422, detail='SMS recipient validation failed')):
            result = self.enroll(payload={**self.payload, 'guardian_phone': '09171234567'})
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

    def test_phone_validation_rejects_bad_contacts_before_saving_or_enrolling(self):
        before = self.snapshot()
        for role in ('Student', 'Faculty', 'Non-teaching Personnel'):
            for phone in ('12345', '+12025550123', '091712345678', '0917abc4567', '0917 1234567'):
                payload = {**self.payload, 'role': role, 'guardian_phone': phone}
                with self.subTest(role=role, phone=phone):
                    self.assertEqual(self.client.post('/api/persons', json=payload).status_code, 422)
                    self.assertEqual(self.client.patch(f'/api/persons/{self.fixture.first.id}', json=payload).status_code, 422)
                    self.assertEqual(self.enroll(payload=payload).status_code, 422)
        self.assertEqual(self.snapshot(), before)

    def test_phone_formats_are_normalized_and_blank_contact_stays_optional(self):
        from app.schemas import PersonCreate
        for phone in ('09171234567', '639171234567', '+639171234567'):
            self.assertEqual(PersonCreate(**{**self.payload, 'guardian_phone': phone}).guardian_phone, '+639171234567')
        for phone in ('', ' ', None):
            self.assertIsNone(PersonCreate(**{**self.payload, 'guardian_phone': phone}).guardian_phone)
