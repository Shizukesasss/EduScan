"""SFace is a no-write experiment; attendance and enrollment retain LBPH."""
import hashlib
import unittest
from dataclasses import replace
from unittest.mock import patch, MagicMock

import numpy as np
from fastapi import HTTPException
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import test_duplicate_enrollment as helpers
from app import main
from app.auth import current_user
from app.database import Base, get_db
from app.models import Person
from app.services import sface_test, face_identity
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError


class SFaceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = helpers.DuplicateEnrollmentTest()
        self.fixture.setUp()
        self.db, self.service = self.fixture.db, self.fixture.service
        self.first, self.second = helpers.face_set(), helpers.face_set(horizontal=True)
        self.fixture.enroll(self.fixture.first, self.first)
        self.fixture.enroll(self.fixture.second, self.second)
        self.features = {}
        for index, faces in enumerate((self.first, self.second)):
            for face in faces:
                vector = np.zeros(128, np.float32)
                vector[index] = 1
                self.features[hashlib.sha256(face.image.tobytes()).hexdigest()] = vector
        self.original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.fixture.admin

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.original)
        self.fixture.tearDown()

    def snapshot(self):
        return {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}

    def feature(self, image, _service):
        value = self.features.get(hashlib.sha256(image.tobytes()).hexdigest())
        if value is None:
            value = np.zeros(128, np.float32)
            value[2] = 1
        return value

    def run_frames(self, observations):
        with patch.object(main, 'biometric_service', self.service), \
             patch.object(self.service, 'process_faces', side_effect=observations), \
             patch.object(sface_test, 'embedding', side_effect=self.feature):
            return main.test_camera_frames([b'test'] * len(observations), self.fixture.engine, 'sface')

    def test_correct_people_and_blinks_without_any_saved_changes(self):
        before = self.snapshot()
        files = {p: p.read_bytes() for p in helpers.Path(self.fixture.directory.name).rglob('*') if p.is_file()}
        observations = [[replace(self.first[0], eye_count=count), replace(self.second[0], eye_count=count)]
                        for count in (2, 0, 2)]
        with patch.object(main, 'record_gate_match') as attendance, \
             patch.object(main, 'queue_enrollment_notice') as sms, \
             patch.object(self.service, 'record_review') as review, patch.object(self.service, 'train') as train:
            result = self.run_frames(observations)
        self.assertEqual(result['matcher'], 'SFace')
        self.assertEqual(result['max_identities_in_frame'], 2)
        self.assertFalse(result['attendance_enabled'])
        self.assertEqual({item['person']['id'] for item in result['results']}, {self.fixture.first.id, self.fixture.second.id})
        self.assertTrue(all(item['camera_checks_passed'] and not item['attendance_event']['recorded'] for item in result['results']))
        for operation in (attendance, sms, review, train):
            operation.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({p: p.read_bytes() for p in helpers.Path(self.fixture.directory.name).rglob('*') if p.is_file()}, files)
        self.assertEqual(self.service._liveness, {})

    def test_unknown_and_ambiguous_faces_are_not_assigned(self):
        unknown = replace(self.first[0], image=np.zeros((200, 200), np.uint8))
        result = self.run_frames([[unknown]])
        self.assertFalse(result['results'][0]['recognized'])
        ambiguous = np.zeros(128, np.float32)
        ambiguous[:2] = 1 / np.sqrt(2)
        self.features[hashlib.sha256(unknown.image.tobytes()).hexdigest()] = ambiguous
        result = self.run_frames([[unknown]])
        self.assertFalse(result['results'][0]['recognized'])
        self.assertIn('uncertain', result['results'][0]['message'])

    def test_same_identity_for_two_faces_is_not_forced(self):
        result = self.run_frames([[self.first[0], self.first[1]]])
        self.assertTrue(all(not item['recognized'] for item in result['results']))

    def test_capture_reports_both_people_even_when_one_leaves_the_final_frame(self):
        result = self.run_frames([[self.first[0]], [self.second[0]]])
        self.assertEqual(result['result_scope'], 'capture')
        self.assertEqual(result['max_identities_in_frame'], 1)
        self.assertEqual({item['person']['id'] for item in result['results']}, {self.fixture.first.id, self.fixture.second.id})
        next_result = self.run_frames([[self.second[0]]])
        self.assertEqual([item['person']['id'] for item in next_result['results']], [self.fixture.second.id])

    def test_completed_blink_survives_a_missed_detection_but_not_the_next_test(self):
        observations = [[replace(self.first[0], eye_count=count)] for count in (2, 0, 2)]
        observations += [HTTPException(422, 'No face'), [replace(self.first[0], eye_count=2)]]
        result = self.run_frames(observations)
        self.assertTrue(result['results'][0]['liveness_verified'])
        next_result = self.run_frames([[replace(self.first[0], eye_count=2)]])
        self.assertFalse(next_result['results'][0]['liveness_verified'])

    def test_read_only_connection_blocks_an_accidental_write(self):
        def unsafe(*_args):
            # Write on the actual test connection, not the fixture session.
            db = _args[0]
            db.add(Person(external_id='must-not-save', full_name='No Write', role='Student', sex='Male'))
            db.commit()
        before = self.snapshot()
        with patch.object(main, 'sface_test_frames', side_effect=unsafe), self.assertRaises(SQLAlchemyError):
            main.test_camera_frames([b'test'], self.fixture.engine, 'sface')
        self.db.rollback()
        self.assertEqual(self.snapshot(), before)

    def test_only_admin_can_use_the_sface_test_route(self):
        with TestClient(main.app) as client, patch.object(main, 'sface_test_frames', return_value={'matcher': 'SFace', 'results': []}) as matcher:
            self.fixture.admin.role = 'teacher'
            response = client.post('/api/biometrics/test', data={'mode': 'sface'}, files={'frames': ('frame.jpg', b'test', 'image/jpeg')})
            self.assertEqual(response.status_code, 403)
            matcher.assert_not_called()
            self.fixture.admin.role = 'admin'
            response = client.post('/api/biometrics/test', data={'mode': 'sface'}, files={'frames': ('frame.jpg', b'test', 'image/jpeg')})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['attendance_enabled'])

    def test_live_gate_does_not_call_the_camera_test_wrapper(self):
        match = {'person': None, 'distance': 90, 'quality': 95, 'box': (0, 0, 100, 100),
                 'liveness_verified': False, 'presentation_verified': None, 'presentation_score': None,
                 'message': 'Unknown face', 'review_id': None}
        with patch.object(main.biometric_service, 'recognize_frames', return_value=[match]) as recognition, \
             patch.object(main, 'sface_test_frames') as experimental, patch.object(main, 'record_gate_match') as attendance:
            result = main.process_gate_frames(BackgroundTasks(), [b'test'], 'isolated-sface-test', self.db)
        recognition.assert_called_once()
        experimental.assert_not_called()
        attendance.assert_not_called()
        self.assertFalse(result['results'][0]['recognized'])

    def test_main_scanner_preview_matches_both_people_without_writes(self):
        before = self.snapshot()
        files = {p: p.read_bytes() for p in helpers.Path(self.fixture.directory.name).rglob('*') if p.is_file()}
        observations = [[replace(self.first[0], eye_count=count), replace(self.second[0], eye_count=count)]
                        for count in (2, 0, 2)]
        with TestClient(main.app) as client, patch.object(main, 'biometric_service', self.service), \
             patch.object(self.service, 'process_faces', side_effect=observations), \
             patch.object(main, 'record_gate_match') as attendance, \
             patch.object(main, 'dispatch_record_by_id') as sms, \
             patch.object(self.service, 'record_review') as review, \
             patch.object(self.service, 'train') as train, \
             patch.object(main.gate_presence, 'observe') as presence:
            response = client.post('/api/biometrics/recognize-preview',
                                   files=[('frames', ('frame.jpg', b'fixture', 'image/jpeg'))] * 3)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result['preview_only'])
        self.assertFalse(result['attendance_enabled'])
        self.assertEqual({item['person']['id'] for item in result['results']}, {self.fixture.first.id, self.fixture.second.id})
        self.assertTrue(all(item['camera_checks_passed'] and not item['attendance_event']['recorded'] for item in result['results']))
        for operation in (attendance, sms, review, train, presence):
            operation.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({p: p.read_bytes() for p in helpers.Path(self.fixture.directory.name).rglob('*') if p.is_file()}, files)
        self.assertEqual(self.service._liveness, {})

    def test_main_scanner_preview_blocks_accidental_database_write(self):
        before = self.snapshot()
        def unsafe_recognition(db, *_args, **_kwargs):
            db.add(Person(external_id='MUST-NOT-SAVE', full_name='Unsafe write', role='Student'))
            db.commit()
        with TestClient(main.app, raise_server_exceptions=False) as client, \
             patch.object(main, 'biometric_service', self.service), \
             patch.object(self.service, 'recognize_frames', side_effect=unsafe_recognition):
            response = client.post('/api/biometrics/recognize-preview', files={'frames': ('frame.jpg', b'fixture', 'image/jpeg')})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.snapshot(), before)

    def test_main_scanner_preview_requires_admin_and_valid_uploads(self):
        with TestClient(main.app) as client, patch.object(main, 'test_camera_frames') as recognition:
            self.fixture.admin.role = 'teacher'
            response = client.post('/api/biometrics/recognize-preview', files={'frames': ('frame.jpg', b'fixture', 'image/jpeg')})
            self.assertEqual(response.status_code, 403)
            self.fixture.admin.role = 'admin'
            response = client.post('/api/biometrics/recognize-preview')
            self.assertEqual(response.status_code, 422)
            response = client.post('/api/biometrics/recognize-preview',
                                   files=[('frames', ('frame.jpg', b'fixture', 'image/jpeg'))] * 41)
            self.assertEqual(response.status_code, 422)
            recognition.assert_not_called()

    def test_model_integrity_and_invalid_outputs_fail_closed(self):
        self.assertEqual(hashlib.sha256(face_identity.MODEL.read_bytes()).hexdigest(), face_identity.MODEL_SHA256)
        with patch.object(self.service, '_human_detections', return_value=self.fixture.human_detection()[None, :]), \
             patch.object(face_identity, '_network', None), patch.object(face_identity, 'MODEL_SHA256', 'invalid'):
            with self.assertRaises(HTTPException) as failure:
                face_identity.embedding(self.first[0].image, self.service)
            self.assertEqual(failure.exception.status_code, 503)
        network = MagicMock()
        network.feature.return_value = np.full((1, 128), np.nan, np.float32)
        with patch.object(self.service, '_human_detections', return_value=self.fixture.human_detection()[None, :]), \
             patch.object(face_identity, '_network', network), self.assertRaises(HTTPException):
            face_identity.embedding(self.first[0].image, self.service)


if __name__ == '__main__':
    unittest.main()
