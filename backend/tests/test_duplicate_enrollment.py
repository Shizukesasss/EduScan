"""Enrollment regression checks using synthetic, non-person images."""
from __future__ import annotations

import hashlib
import copy
from dataclasses import replace
from datetime import datetime, timedelta
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="eduscan-duplicate-test-")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EDUSCAN_DATA_DIR"] = TEST_DIRECTORY.name
os.environ["EDUSCAN_SECRET_KEY"] = "isolated-duplicate-enrollment-test-secret"
os.environ["BIOMETRIC_ENABLED"] = "true"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"

from app.database import Base  # noqa: E402
from app.models import AttendanceEvent, BiometricAuditEvent, BiometricModel, BiometricSample, Person, User  # noqa: E402
from app.services import biometrics  # noqa: E402
from app.services.biometrics import BiometricService, ProcessedFace  # noqa: E402


def face_set(horizontal: bool = False, offset: int = 0) -> list[ProcessedFace]:
    result = []
    for index in range(15):
        image = np.full((200, 200), 50 + index, dtype=np.uint8)
        for position in range(12 + offset, 200, 25):
            start, end = ((0, position), (199, position)) if horizontal else ((position, 0), (position, 199))
            cv2.line(image, start, end, 200, 8)
        cv2.circle(image, (50 + index * 3, 80), 3, 100, -1)
        if horizontal:
            # Rotating stripes alone has nearly identical LBPH texture; distinct identities need distinct texture.
            image = cv2.add(image, np.random.default_rng(index).integers(0, 20, image.shape, dtype=np.uint8))
        success, encoded = cv2.imencode(".png", image)
        assert success
        result.append(ProcessedFace(image, encoded.tobytes(), 95, eye_count=0 if index == 6 else 2,
                                    human_verified=True, presentation_score=0.99))
    return result


class DuplicateEnrollmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.directory = tempfile.TemporaryDirectory(dir=TEST_DIRECTORY.name)
        base = Path(self.directory.name)
        self.paths = patch.multiple(biometrics, BIOMETRIC_DIR=base / "samples", MODEL_DIR=base / "models")
        self.paths.start()
        (base / "models").mkdir()
        self.service = BiometricService()
        def synthetic_identity(image):
            horizontal = float(cv2.Sobel(image, cv2.CV_32F, 1, 0).var())
            vertical = float(cv2.Sobel(image, cv2.CV_32F, 0, 1).var())
            vector = np.zeros(128, np.float32)
            vector[0 if horizontal > vertical * 2 else 1 if vertical > horizontal * 2 else 2] = 1
            return vector
        self.identity = patch.object(self.service, '_identity_feature', side_effect=synthetic_identity)
        self.identity.start()
        self.admin = User(username="admin", password_hash="unused", full_name="Test Administrator", role="admin", must_change_password=False)
        self.first = Person(external_id="ONE", full_name="First Person", sex="Female", role="Student", biometric_consent=True)
        self.second = Person(external_id="TWO", full_name="Second Person", sex="Male", role="Faculty", biometric_consent=True)
        self.db.add_all([self.admin, self.first, self.second])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        self.paths.stop()
        self.identity.stop()
        self.directory.cleanup()

    def enroll(self, person, faces, replacement=False):
        with patch.object(self.service, "process_frame", side_effect=faces):
            return self.service.enroll(self.db, person, [b"frame"] * len(faces), self.admin,
                                       "Authorized test enrollment", require_existing=replacement)

    def samples(self, person):
        return self.db.scalars(select(BiometricSample).where(BiometricSample.person_id == person.id)).all()

    def test_same_face_cannot_be_enrolled_for_another_role(self):
        self.enroll(self.first, face_set())
        before_models = self.db.scalars(select(BiometricModel)).all()
        before_files = list(Path(self.directory.name).rglob("*.enc"))
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.second, face_set())
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(failure.exception.detail["code"], "duplicate_face")
        self.assertEqual(failure.exception.detail["existing_person_id"], self.first.id)
        self.assertEqual(len(self.samples(self.first)), 15)
        self.assertEqual(self.samples(self.second), [])
        self.assertEqual([m.id for m in self.db.scalars(select(BiometricModel))], [m.id for m in before_models])
        self.assertEqual(list(Path(self.directory.name).rglob("*.enc")), before_files)
        self.assertEqual(len(self.db.scalars(select(BiometricAuditEvent)).all()), 1)

    def test_new_captures_of_same_face_are_rejected_by_lbph(self):
        self.enroll(self.first, face_set())
        new_frames = face_set(offset=1)
        self.assertTrue(set(s.sha256 for s in self.samples(self.first)).isdisjoint(
            hashlib.sha256(face.encoded).hexdigest() for face in new_frames))
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.second, new_frames)
        self.assertEqual(failure.exception.detail["code"], "duplicate_face")

    def test_distinct_face_can_be_enrolled(self):
        self.enroll(self.first, face_set())
        result = self.enroll(self.second, face_set(horizontal=True))
        self.assertEqual(result["accepted"], 15)
        self.assertEqual(result["model"]["person_count"], 2)

    def test_lbph_texture_similarity_cannot_block_a_different_identity(self):
        self.enroll(self.first, face_set())
        before = {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
        self.service._check_duplicate_enrollment(self.db, self.second, face_set(horizontal=True))
        self.assertEqual({table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}, before)

    def test_shared_identity_matcher_catches_duplicates_without_lbph_agreement(self):
        self.enroll(self.first, face_set())
        with patch.object(cv2.face, 'LBPHFaceRecognizer_create') as checker:
            with self.assertRaises(HTTPException) as failure:
                self.service._check_duplicate_enrollment(self.db, self.second, face_set(offset=1))
        self.assertEqual(failure.exception.detail['code'], 'duplicate_face')
        checker.assert_not_called()

    def test_isolated_near_matches_do_not_block_distinct_face(self):
        self.enroll(self.first, face_set())
        threshold = min(biometrics.settings.lbph_threshold, self.service.runtime_config(self.db)['threshold'])
        checker = MagicMock()
        results = iter([((self.first.id, threshold * 1.02),) * 10] * 2 + [()] * 13)
        def predictions(_image, collector):
            collector.getResults.return_value = next(results)
        checker.predict_collect.side_effect = predictions
        with patch.object(cv2.face, 'LBPHFaceRecognizer_create', return_value=checker), \
             patch.object(cv2.face, 'StandardCollector_create', side_effect=lambda _threshold: MagicMock()):
            self.service._check_duplicate_enrollment(self.db, self.second, face_set(horizontal=True))

    def test_known_face_cannot_be_hidden_in_a_mixed_dataset(self):
        self.enroll(self.first, face_set())
        frames = face_set(offset=1)[:3] + face_set(horizontal=True)[:12]
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.second, frames)
        self.assertEqual(failure.exception.detail['code'], 'duplicate_face')
        self.assertEqual(self.samples(self.second), [])

    def test_non_nearest_identity_is_also_checked_for_duplicates(self):
        self.enroll(self.first, face_set())
        other = Person(external_id='THREE', full_name='Other Person', role='Student', sex='Male', biometric_consent=True)
        self.db.add(other)
        self.db.commit()
        self.enroll(other, face_set(horizontal=True))
        checker = MagicMock()
        def predictions(_image, collector):
            collector.getResults.return_value = ((other.id, 1.0), (self.first.id, 20.0))
        checker.predict_collect.side_effect = predictions
        with patch.object(cv2.face, 'LBPHFaceRecognizer_create', return_value=checker), \
             patch.object(cv2.face, 'StandardCollector_create', side_effect=lambda _threshold: MagicMock()):
            with self.assertRaises(HTTPException) as failure:
                self.enroll(self.second, face_set(offset=1))
        self.assertEqual(failure.exception.detail['existing_person_id'], self.first.id)

    def test_enrollment_and_reenrollment_do_not_record_attendance(self):
        self.enroll(self.first, face_set())
        self.enroll(self.first, face_set(offset=1), replacement=True)
        self.assertEqual(len(self.samples(self.first)), 15)
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])

    def test_same_person_can_replace_their_own_enrollment(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        result = self.enroll(self.first, face_set(offset=1), replacement=True)
        self.assertEqual(result["action"], "updated")
        self.assertEqual(len(self.samples(self.first)), 15)

    def test_gate_model_still_recognizes_distinct_enrolled_identities(self):
        first_frames, second_frames = face_set(), face_set(horizontal=True)
        self.enroll(self.first, first_frames)
        self.enroll(self.second, second_frames)
        with patch.object(self.service, "process_faces", return_value=[first_frames[0], second_frames[0]]), patch.object(self.service, "verify_liveness", return_value=(True, "Verified")):
            matches = self.service.recognize_many(self.db, b"two-face-frame")
        self.assertEqual({match['person'].id for match in matches}, {self.first.id, self.second.id})

    def test_normal_gate_uses_identity_features_when_lbph_prefers_the_wrong_person(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        checker = MagicMock()
        def predictions(_image, collector):
            collector.getResults.return_value = ((self.second.id, 44.01), (self.first.id, 70.01))
        checker.predict_collect.side_effect = predictions
        with patch.object(self.service, '_active_recognizer', return_value=(checker, None)), \
             patch.object(cv2.face, 'StandardCollector_create', side_effect=lambda _threshold: MagicMock()), \
             patch.object(self.service, 'process_faces', return_value=[face_set()[0], face_set(horizontal=True)[0]]), \
             patch.object(self.service, 'verify_liveness', return_value=(True, 'Verified')):
            results = self.service.recognize_frames(self.db, [b'group'], diagnostics={})
        self.assertEqual({item['person'].id for item in results}, {self.first.id, self.second.id})
        first = next(item for item in results if item['person'].id == self.first.id)
        self.assertEqual(first['distance'], 70.01)
        self.assertAlmostEqual(first['identity_similarity'], 1)

    def test_normal_gate_rejects_unknown_and_ambiguous_identity_features(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        for scores in ([(self.first.id, .2), (self.second.id, .1)],
                       [(self.first.id, .7), (self.second.id, .65)]):
            with self.subTest(scores=scores), patch.object(self.service, '_identity_scores', return_value=scores), \
                 patch.object(self.service, 'process_faces', return_value=[face_set()[0]]), \
                 patch.object(self.service, 'verify_liveness') as blink:
                result = self.service.recognize_frames(self.db, [b'test'], diagnostics={})
            self.assertIsNone(result[0]['person'])
            self.assertFalse(result[0]['liveness_verified'])
            blink.assert_not_called()

    def test_normal_gate_never_falls_back_to_lbph_if_identity_verification_fails(self):
        self.enroll(self.first, face_set())
        with patch.object(self.service, '_identity_scores', side_effect=HTTPException(503, 'Identity verifier unavailable')), \
             patch.object(self.service, 'process_faces', return_value=[face_set()[0]]):
            with self.assertRaises(HTTPException) as failure:
                self.service.recognize_frames(self.db, [b'test'], diagnostics={})
        self.assertEqual(failure.exception.status_code, 503)

    def test_main_group_endpoint_records_each_fixture_once_and_holds_the_visit(self):
        self._check_main_group_attendance(second_blinks=True)

    def test_main_group_endpoint_does_not_record_a_person_without_their_own_blink(self):
        self._check_main_group_attendance(second_blinks=False)

    def _check_main_group_attendance(self, second_blinks):
        from fastapi.testclient import TestClient
        from app import main
        from app.auth import current_user
        from app.database import get_db
        from app.services.gate_presence import GatePresence
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.admin
        observations = [[replace(face_set()[0], eye_count=0 if index == 4 else 2),
                         replace(face_set(horizontal=True)[0], eye_count=0 if second_blinks and index == 6 else 2)]
                        for index in range(40)]
        uploads = [('frames', (f'frame-{index}.jpg', b'isolated-fixture', 'image/jpeg')) for index in range(40)]
        try:
            with TestClient(main.app) as client, patch.object(main, 'biometric_service', self.service), \
                 patch.object(main, 'gate_presence', GatePresence()), \
                 patch.object(main, 'update_gate_export'), patch.object(main, 'dispatch_record_by_id') as sms:
                for repetition in range(2):
                    with patch.object(self.service, 'process_faces', side_effect=observations):
                        response = client.post('/api/biometrics/recognize-many',
                                               data={'station_id': 'isolated-two-person-test'}, files=uploads)
                    self.assertEqual(response.status_code, 200, response.text)
                    results = response.json()['results']
                    self.assertEqual({item['person']['id'] for item in results}, {self.first.id, self.second.id})
                    expected = {self.first.id, self.second.id} if second_blinks else {self.first.id}
                    events = self.db.scalars(select(AttendanceEvent)).all()
                    self.assertEqual({event.person_id for event in events}, expected)
                    self.assertEqual(len(events), len(expected))
                    self.assertTrue(all(event.direction == 'Time In' for event in events))
                    if repetition:
                        self.assertTrue(all(not item['attendance_event']['recorded'] for item in results))
                    else:
                        self.assertEqual({item['person']['id'] for item in results if item['attendance_event']['recorded']}, expected)
                sms.assert_not_called()
        finally:
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(original)

    def test_burst_catches_blink_without_per_frame_database_lookups(self):
        faces = face_set()
        self.enroll(self.first, faces)
        observations = [replace(faces[0], eye_count=count) for count in [2, 2, 0, 2] + [2] * 12]
        with patch.object(self.service, 'process_faces', side_effect=[[face] for face in observations]), \
             patch.object(self.service, '_active_recognizer', wraps=self.service._active_recognizer) as model_load, \
             patch.object(self.service, 'runtime_config', wraps=self.service.runtime_config) as configuration, \
             patch.object(self.service, 'record_review', wraps=self.service.record_review) as review:
            results = self.service.recognize_frames(self.db, [b'frame'] * 16)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['person'].id, self.first.id)
        self.assertTrue(results[0]['liveness_verified'])
        self.assertEqual(model_load.call_count, 1)
        self.assertEqual(configuration.call_count, 1)
        review.assert_not_called()

    def test_burst_without_blink_does_not_verify_liveness(self):
        faces = face_set()
        self.enroll(self.first, faces)
        with patch.object(self.service, 'process_faces', return_value=[replace(faces[0], eye_count=2)]):
            result = self.service.recognize_frames(self.db, [b'frame'] * 16)
        self.assertFalse(result[0]['liveness_verified'])
        self.assertEqual(len(self.db.scalars(select(biometrics.RecognitionReview)).all()), 1)

    def test_diagnostics_report_both_identity_distances_without_writes(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        before = {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
        files = {path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}
        diagnostics = {}
        with patch.object(self.service, 'process_faces', return_value=[face_set()[0]]):
            self.service.recognize_frames(self.db, [b'test'], diagnostics=diagnostics)
        comparison = diagnostics['identity_comparisons'][0]
        self.assertEqual(comparison['face'], 1)
        self.assertEqual({candidate['name'] for candidate in comparison['candidates']}, {self.first.full_name, self.second.full_name})
        self.assertEqual(comparison['candidates'][0]['name'], self.first.full_name)
        self.assertAlmostEqual(comparison['candidates'][0]['similarity'], 1)
        self.assertEqual({table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}, before)
        self.assertEqual({path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}, files)

    def test_burst_returns_only_people_in_the_latest_frame(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        with patch.object(self.service, 'process_faces', side_effect=[[face_set()[0]], [face_set(horizontal=True)[0]]]):
            result = self.service.recognize_frames(self.db, [b'old', b'current'], diagnostics={})
        self.assertEqual([item['person'].id for item in result], [self.second.id])

    def test_no_face_at_end_does_not_return_an_earlier_identity(self):
        self.enroll(self.first, face_set())
        with patch.object(self.service, 'process_faces', side_effect=[
                [face_set()[0]], HTTPException(422, 'No frontal human face was detected')]):
            with self.assertRaises(HTTPException) as failure:
                self.service.recognize_frames(self.db, [b'old', b'empty'], diagnostics={})
        self.assertEqual(failure.exception.status_code, 422)

    def test_group_identity_collision_is_not_assigned_to_the_first_face(self):
        self.enroll(self.first, face_set())
        before = {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
        with patch.object(self.service, 'process_faces', return_value=face_set()[:2]):
            result = self.service.recognize_frames(self.db, [b'group'], diagnostics={})
        self.assertEqual(len(result), 2)
        self.assertTrue(all(item['person'] is None and not item['liveness_verified'] for item in result))
        self.assertTrue(all('same identity' in item['message'] for item in result))
        self.assertEqual({table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}, before)

    def test_group_recognizes_two_distinct_enrolled_people_independently(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        observations = [[replace(face_set()[0], eye_count=count),
                         replace(face_set(horizontal=True)[0], eye_count=count)] for count in (2, 0, 2)]
        with patch.object(self.service, 'process_faces', side_effect=observations):
            result = self.service.recognize_frames(self.db, [b'group'] * 3, diagnostics={})
        self.assertEqual({item['person'].id for item in result}, {self.first.id, self.second.id})
        self.assertTrue(all(item['liveness_verified'] for item in result))

    def test_diagnostics_never_change_live_blink_state_or_review_records(self):
        self.enroll(self.first, face_set())
        face = face_set()[0]
        review = biometrics.RecognitionReview(id='existing-review', face_signature=hashlib.sha256(f'person:{self.first.id}'.encode()).hexdigest(),
            candidate_person_id=self.first.id, candidate_name=self.first.full_name, review_type='Liveness', reason='Existing live review', status='Open')
        self.db.add(review)
        self.db.commit()
        self.service._liveness[('default', self.first.id)] = {'stage': 'closed', 'expires_at': datetime.utcnow() + timedelta(seconds=30)}
        before = copy.deepcopy(self.service._liveness)
        for counts, score, expected_live in (((2, 2, 2), .99, False), ((2, 0, 2), .99, True), ((2, 0, 2), .01, True)):
            diagnostics = {}
            with patch.object(self.service, 'process_faces', side_effect=[[replace(face, eye_count=count, presentation_score=score)] for count in counts]):
                result = self.service.recognize_frames(self.db, [b'test'] * 3, diagnostics=diagnostics, verified_present={self.first.id})
            self.assertEqual(result[0]['liveness_verified'], expected_live)
            self.assertEqual(diagnostics['frames_checked'], 3)
            self.assertEqual(diagnostics['max_faces_in_frame'], 1)
            self.assertEqual(diagnostics['identity_comparisons'][0]['candidates'][0]['name'], self.first.full_name)
            self.assertEqual(self.service._liveness, before)
            self.db.refresh(review)
            self.assertEqual(review.status, 'Open')
            self.assertIsNone(review.resolved_at)
            self.assertEqual(self.db.scalars(select(biometrics.RecognitionReview)).all(), [review])

    def test_camera_test_api_is_read_only_for_success_replay_and_groups_up_to_ten(self):
        from fastapi.testclient import TestClient
        from app import main
        from app.auth import current_user
        from app.database import get_db
        from app.models import SmsOutbox
        first, second = face_set()[0], face_set(horizontal=True)[0]
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        files_before = {path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}
        snapshots = lambda: {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
        before = snapshots()
        original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.admin
        client = TestClient(main.app)
        unknown = replace(first, image=np.zeros((200, 200), dtype=np.uint8))
        recognizer, model = self.service._active_recognizer(self.db)
        checker = MagicMock(wraps=recognizer)
        checker.predict.side_effect = lambda image: (-1, 100.0) if np.array_equal(image, unknown.image) else recognizer.predict(image)
        try:
            for group_count, score in ((3, .99), (3, .01), (5, .99), (10, .99)):
                observations = [[replace(first, eye_count=count, presentation_score=score), replace(second, eye_count=count)] + [unknown] * (group_count - 2)
                                for count in [2, 0, 2] + [2] * 37]
                with patch.object(main, 'biometric_service', self.service), \
                     patch.object(self.service, '_active_recognizer', return_value=(checker, model)), \
                     patch.object(self.service, 'process_faces', side_effect=observations), \
                     patch.object(main, 'record_gate_match') as attendance, patch.object(main, 'update_gate_export') as export, \
                     patch.object(main, 'dispatch_record_by_id') as sms, patch.object(main.gate_presence, 'observe') as presence:
                    uploads = [('frames', (f'{i}.jpg', b'test', 'image/jpeg')) for i in range(40)]
                    response = client.post('/api/biometrics/test', files=uploads)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertTrue(result['test_mode'])
                self.assertFalse(result['attendance_enabled'])
                self.assertEqual(result['max_faces_in_frame'], group_count)
                self.assertEqual(result['frames_checked'], 40)
                self.assertTrue(all(not item['attendance_event']['recorded'] for item in result['results']))
                self.assertEqual(sum(item['camera_checks_passed'] for item in result['results']), 2)
                for operation in (attendance, export, sms, presence):
                    operation.assert_not_called()
                self.assertEqual(snapshots(), before)
                self.assertEqual({path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}, files_before)
                self.assertEqual(self.db.scalars(select(SmsOutbox)).all(), [])
                self.assertEqual(self.service._liveness, {})
        finally:
            client.close()
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(original)

    def test_diagnostic_connection_blocks_an_accidental_database_write(self):
        from app import main
        from sqlalchemy.exc import SQLAlchemyError
        from sqlalchemy import text
        def unsafe_recognition(db, *_args, **_kwargs):
            db.add(biometrics.RecognitionReview(id='must-not-save', face_signature='test', review_type='Liveness', reason='Simulated accidental test write'))
            db.commit()
            return []
        with patch.object(main.biometric_service, 'recognize_frames', side_effect=unsafe_recognition):
            with self.assertRaises(SQLAlchemyError):
                main.test_camera_frames([b'test'], self.engine)
        self.assertEqual(self.db.scalars(select(biometrics.RecognitionReview)).all(), [])
        self.assertEqual(self.db.scalar(text('PRAGMA query_only')), 0)

    def test_enrollment_camera_test_uses_real_checks_without_saving(self):
        from app import main
        self.enroll(self.first, face_set())
        snapshots = lambda: {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
        before = snapshots()
        files = {path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}
        fresh = face_set(horizontal=True)
        cases = [(fresh, True, None),
                 (face_set(), False, 'duplicate_face'),
                 ([replace(face, eye_count=2) for face in fresh], True, None),
                 ([replace(face, presentation_score=.01) for face in fresh], True, None),
                 ([HTTPException(status_code=422, detail='More than one face was detected')] * 15, False, None)]
        with patch.object(main, 'biometric_service', self.service), \
             patch.object(self.service, 'train') as train, \
             patch.object(self.service, 'record_review') as review, \
             patch.object(main, 'queue_enrollment_notice') as sms:
            for frames, passed, code in cases:
                with self.subTest(code=code), patch.object(self.service, 'process_frame', side_effect=frames):
                    result = main.test_camera_frames([b'frame'] * len(frames), self.engine, 'enrollment')
                self.assertTrue(result['test_mode'])
                self.assertFalse(result['attendance_enabled'])
                self.assertEqual(result['results'], [])
                self.assertEqual(result['enrollment']['can_enroll'], passed)
                if code:
                    self.assertEqual(result['enrollment']['code'], code)
                self.assertEqual(snapshots(), before)
                self.assertEqual({path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}, files)
            for operation in (train, review, sms):
                operation.assert_not_called()
        self.assertEqual(self.service._liveness, {})

    def test_enrollment_test_connection_blocks_an_accidental_write(self):
        from app import main
        from sqlalchemy.exc import SQLAlchemyError
        def unsafe_duplicate_check(db, *_args):
            db.add(Person(external_id='must-not-save', full_name='Test only', role='Student', sex='Male'))
            db.commit()
        before = self.db.scalars(select(Person)).all()
        with patch.object(main, 'biometric_service', self.service), \
             patch.object(self.service, 'process_frame', side_effect=face_set()), \
             patch.object(self.service, '_check_duplicate_enrollment', side_effect=unsafe_duplicate_check):
            with self.assertRaises(SQLAlchemyError):
                main.test_camera_frames([b'frame'] * 15, self.engine, 'enrollment')
        self.assertEqual(self.db.scalars(select(Person)).all(), before)

    def test_duplicate_checks_cover_all_roles_in_enrollment_and_camera_test(self):
        from app import main
        self.enroll(self.first, face_set())
        for role in ('Student', 'Faculty', 'Non-teaching Personnel'):
            self.first.role = role
            self.db.commit()
            before = {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
            files = {path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as failure:
                    self.enroll(self.second, face_set())
                self.assertEqual(failure.exception.detail['code'], 'duplicate_face')
                with patch.object(main, 'biometric_service', self.service), \
                     patch.object(self.service, 'process_frame', side_effect=face_set()):
                    result = main.test_camera_frames([b'frame'] * 15, self.engine, 'enrollment')
                self.assertFalse(result['enrollment']['can_enroll'])
                self.assertEqual(result['enrollment']['existing_person_id'], self.first.id)
                self.assertEqual({table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}, before)
                self.assertEqual({path: path.read_bytes() for path in Path(self.directory.name).rglob('*.enc')}, files)

    def test_enrollment_camera_test_ignores_unverified_background_candidates(self):
        from app import main
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220], [5, 5, 75, 75]])
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        before = {table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}
        with patch.object(main, 'biometric_service', self.service), \
             patch.object(self.service, 'detector', haar), \
             patch.object(self.service, '_human_detections', return_value=self.human_detection()[None, :]), \
             patch.object(self.service, '_processed_face', side_effect=face_set()):
            result = main.test_camera_frames([data.tobytes()] * 15, self.engine, 'enrollment')
        self.assertTrue(result['enrollment']['can_enroll'])
        self.assertEqual({table.name: self.db.execute(select(table)).all() for table in Base.metadata.sorted_tables}, before)
        self.assertEqual(list(Path(self.directory.name).rglob('*.enc')), [])

    def test_camera_test_requires_admin_and_rejects_invalid_burst_size(self):
        from fastapi.testclient import TestClient
        from app import main
        from app.auth import current_user
        from app.database import get_db
        original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.admin
        client = TestClient(main.app)
        try:
            with patch.object(main.biometric_service, 'recognize_frames') as recognize:
                for role in ('scanner', 'teacher'):
                    self.admin.role = role
                    response = client.post('/api/biometrics/test', files=[('frames', ('test.jpg', b'test', 'image/jpeg'))])
                    self.assertEqual(response.status_code, 403, response.text)
                self.admin.role = 'admin'
                for uploads in ([], [('frames', ('test.jpg', b'test', 'image/jpeg'))] * 41):
                    response = client.post('/api/biometrics/test', files=uploads)
                    self.assertEqual(response.status_code, 422, response.text)
                recognize.assert_not_called()
            with patch.object(main, 'biometric_service', self.service), \
                 patch.object(self.service, 'process_frame', side_effect=face_set()):
                uploads = [('frames', (f'{index}.jpg', b'frame', 'image/jpeg')) for index in range(15)]
                response = client.post('/api/biometrics/test', data={'mode': 'enrollment'}, files=uploads)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['enrollment']['can_enroll'])
                self.assertEqual(self.samples(self.first), [])
                response = client.post('/api/biometrics/test', data={'mode': 'invalid'}, files=uploads)
                self.assertEqual(response.status_code, 422, response.text)
        finally:
            self.admin.role = 'admin'
            client.close()
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(original)

    def test_restored_single_and_group_routes_return_no_presentation_result(self):
        from fastapi.testclient import TestClient
        from app import main
        from app.auth import current_user
        from app.database import get_db
        self.enroll(self.first, face_set())
        original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.admin
        try:
            with TestClient(main.app) as client, patch.object(main, 'biometric_service', self.service), \
                 patch.object(self.service, 'process_faces', return_value=[replace(face_set()[0], eye_count=2)]), \
                 patch.object(main, 'record_gate_match') as attendance:
                for route in ('recognize', 'recognize-many'):
                    response = client.post('/api/biometrics/' + route,
                                           files={'frame': ('frame.jpg', b'test', 'image/jpeg')})
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    item = result if route == 'recognize' else result['results'][0]
                    self.assertTrue(item['recognized'])
                    self.assertEqual(item['person']['id'], self.first.id)
                    self.assertAlmostEqual(item['identity_similarity'], 1)
                    self.assertIsNone(item['presentation_verified'])
                    self.assertIsNone(item['presentation_score'])
                    self.assertFalse(item['liveness_verified'])
                attendance.assert_not_called()
        finally:
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(original)

    def test_closed_then_open_eyes_cannot_skip_the_full_blink(self):
        face = face_set()[0]
        config = self.service.runtime_config(self.db)
        results = [self.service.verify_liveness(self.db, self.first, replace(face, eye_count=count), config=config)[0]
                   for count in (0, 2, 2, 0, 2)]
        self.assertEqual(results, [False, False, False, False, True])

    def test_blink_challenge_is_scoped_to_the_station(self):
        face = face_set()[0]
        config = self.service.runtime_config(self.db)
        for count in (2, 0):
            self.service.verify_liveness(self.db, self.first, replace(face, eye_count=count), config=config, station_id='a')
        self.assertFalse(self.service.verify_liveness(self.db, self.first, replace(face, eye_count=2), config=config, station_id='b')[0])
        self.assertTrue(self.service.verify_liveness(self.db, self.first, replace(face, eye_count=2), config=config, station_id='a')[0])

    def test_expired_blink_state_cannot_verify_and_is_removed(self):
        expired = {'stage': 'closed', 'expires_at': datetime.utcnow() - timedelta(seconds=1)}
        self.service._liveness[('old-station', self.first.id)] = expired.copy()
        self.service._liveness[('default', self.first.id)] = expired.copy()
        live, _ = self.service.verify_liveness(self.db, self.first, replace(face_set()[0], eye_count=2))
        self.assertFalse(live)
        self.assertNotIn(('old-station', self.first.id), self.service._liveness)

    def test_already_recorded_visit_does_not_restart_blink_challenge(self):
        faces = face_set()
        self.enroll(self.first, faces)
        with patch.object(self.service, 'process_faces', return_value=[replace(faces[0], eye_count=2)]), \
             patch.object(self.service, 'verify_liveness', wraps=self.service.verify_liveness) as blink:
            result = self.service.recognize_frames(self.db, [b'frame'] * 16, verified_present={self.first.id})
        self.assertTrue(result[0]['liveness_verified'])
        blink.assert_not_called()
        self.assertEqual(self.db.scalars(select(biometrics.RecognitionReview)).all(), [])

    def test_replacement_with_someone_elses_face_preserves_original(self):
        self.enroll(self.first, face_set())
        self.enroll(self.second, face_set(horizontal=True))
        originals = [(s.id, s.encrypted_path) for s in self.samples(self.second)]
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.second, face_set(offset=1), replacement=True)
        self.assertEqual(failure.exception.detail["code"], "duplicate_face")
        self.assertEqual([(s.id, s.encrypted_path) for s in self.samples(self.second)], originals)
        self.assertTrue(all(Path(path).exists() for _, path in originals))

    def test_inactive_identity_still_owns_its_enrolled_face(self):
        self.enroll(self.first, face_set())
        self.first.active = False
        self.db.commit()
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.second, face_set())
        self.assertEqual(failure.exception.detail["code"], "duplicate_face")

    def test_missing_samples_do_not_silently_skip_duplicate_check(self):
        self.enroll(self.first, face_set())
        self.samples(self.first)[0].encrypted_path = str(Path(self.directory.name) / "unavailable.enc")
        self.db.commit()
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.second, face_set(horizontal=True))
        self.assertEqual(failure.exception.detail["code"], "identity_verifier_unavailable")
        self.assertEqual(self.samples(self.second), [])

    def test_postgresql_busy_enrollment_does_not_run_check_or_write(self):
        busy_db = MagicMock()
        busy_db.get_bind.return_value.dialect.name = "postgresql"
        busy_db.scalar.return_value = False
        with patch.object(self.service, "_enroll") as enroll_body:
            with self.assertRaises(HTTPException) as failure:
                self.service.enroll(busy_db, self.second, [], self.admin, "Authorized enrollment")
            self.assertEqual(failure.exception.status_code, 409)
            enroll_body.assert_not_called()

    @staticmethod
    def human_detection():
        return np.array([60, 40, 180, 220, 110, 110, 185, 110, 148, 155, 120, 205, 178, 205, 0.99], dtype=np.float32)

    def test_human_landmarks_require_eyes_nose_and_mouth_arrangement(self):
        detection = self.human_detection()
        self.assertTrue(self.service._human_landmarks_valid(detection))
        for index, value in ((5, 200), (9, 80), (11, 80), (14, 0.6), (4, np.nan)):
            invalid = detection.copy()
            invalid[index] = value
            self.assertFalse(self.service._human_landmarks_valid(invalid))

    def test_verified_face_must_overlap_the_face_crop(self):
        self.assertGreater(self.service._face_overlap((60, 40, 180, 220), self.human_detection()), 0.4)
        self.assertLess(self.service._face_overlap((0, 0, 30, 30), self.human_detection()), 0.4)

    def test_extra_human_face_rejects_enrollment(self):
        detector = MagicMock()
        detector.detect.return_value = (1, np.stack([self.human_detection()] * 2))
        self.service._human_detector = detector
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220]])
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        with patch.object(self.service, 'detector', haar), self.assertRaises(HTTPException) as failure:
            self.service.process_frame(data.tobytes())
        self.assertEqual(failure.exception.status_code, 422)

    def test_real_detector_rejects_false_haar_detection_of_object(self):
        success, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        self.assertTrue(success)
        detector = MagicMock()
        detector.detectMultiScale.return_value = np.array([[60, 40, 180, 220]])
        with patch.object(self.service, 'detector', detector), patch.object(self.service, '_processed_face') as crop:
            with self.assertRaises(HTTPException) as failure:
                self.service.process_frame(data.tobytes())
            self.assertEqual(failure.exception.detail['code'], 'human_face_required')
            crop.assert_not_called()

    def test_missing_human_detector_blocks_enrollment(self):
        with patch.object(biometrics, 'HUMAN_FACE_MODEL', Path(self.directory.name) / 'missing.onnx'):
            with self.assertRaises(HTTPException) as failure:
                self.service._human_detections(np.zeros((300, 300, 3), dtype=np.uint8))
        self.assertEqual(failure.exception.status_code, 503)
        self.assertEqual(failure.exception.detail['code'], 'human_face_verifier_unavailable')

    def test_multiface_checks_humans_once_and_filters_unverified_objects(self):
        detection = self.human_detection()
        second = detection.copy()
        second[[0, 4, 6, 8, 10, 12]] += 300
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220], [360, 40, 180, 220], [0, 0, 30, 30]])
        detector = MagicMock()
        detector.detect.return_value = (1, np.stack([detection, second]))
        self.service._human_detector = detector
        _, data = cv2.imencode('.png', np.zeros((300, 600, 3), dtype=np.uint8))
        with patch.object(self.service, 'detector', haar), patch.object(self.service, '_processed_face', side_effect=[replace(face, presentation_score=None) for face in face_set()[:2]]) as crop:
            result = self.service.process_faces(data.tobytes())
        self.assertEqual(len(result), 2)
        self.assertTrue(all(face.human_verified for face in result))
        self.assertEqual(crop.call_count, 2)
        self.assertTrue(all(face.presentation_score is None for face in result))
        detector.detect.assert_called_once()

    def test_identity_path_keeps_both_verified_faces_even_when_haar_sees_only_one(self):
        detection = self.human_detection()
        second = detection.copy()
        second[[0, 4, 6, 8, 10, 12]] += 300
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220]])
        _, data = cv2.imencode('.png', np.zeros((300, 600, 3), dtype=np.uint8))
        features = [np.eye(128, dtype=np.float32)[0], np.eye(128, dtype=np.float32)[1]]
        with patch.object(self.service, 'detector', haar), \
             patch.object(self.service, '_human_detections', return_value=np.stack([detection, second])) as human, \
             patch.object(self.service, '_processed_face', side_effect=face_set()[:2]), \
             patch.object(biometrics, 'feature_from_detection', side_effect=features) as align:
            faces = self.service.process_faces(data.tobytes(), with_identity=True)
        self.assertEqual(len(faces), 2)
        haar.detectMultiScale.assert_not_called()
        human.assert_called_once()
        self.assertEqual(align.call_count, 2)
        for index, expected in enumerate((detection, second)):
            self.assertEqual(align.call_args_list[index].args[0].shape, (300, 600, 3))
            np.testing.assert_allclose(align.call_args_list[index].args[1], expected)
            np.testing.assert_allclose(faces[index].identity_feature, features[index])

    def test_identity_path_does_not_accept_unverified_landmarks(self):
        detection = self.human_detection()
        detection[14] = .6
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        with patch.object(self.service, '_human_detections', return_value=detection[None, :]), \
             patch.object(biometrics, 'feature_from_detection') as align:
            with self.assertRaises(HTTPException):
                self.service.process_faces(data.tobytes(), with_identity=True)
        align.assert_not_called()

    def test_one_verified_detection_cannot_authorize_two_crops(self):
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220]] * 2)
        self.service._human_detector = MagicMock()
        self.service._human_detector.detect.return_value = (1, self.human_detection()[None, :])
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        with patch.object(self.service, 'detector', haar), patch.object(self.service, '_processed_face', return_value=face_set()[0]):
            self.assertEqual(len(self.service.process_faces(data.tobytes())), 1)

    def test_enrollment_ignores_background_candidate_without_a_verified_human_face(self):
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220], [5, 5, 75, 75]])
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        with patch.object(self.service, 'detector', haar), \
             patch.object(self.service, '_human_detections', return_value=self.human_detection()[None, :]), \
             patch.object(self.service, '_processed_face', return_value=face_set()[0]) as crop:
            face = self.service.process_frame(data.tobytes())
        self.assertTrue(face.human_verified)
        crop.assert_called_once()

    def test_all_recognition_routes_reject_objects_without_attendance(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth import current_user
        from app.database import get_db
        haar = MagicMock()
        haar.detectMultiScale.return_value = np.array([[60, 40, 180, 220]])
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        original = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[current_user] = lambda: self.admin
        try:
            with TestClient(app) as client, patch('app.main.biometric_service', self.service), \
                 patch.object(self.service, 'detector', haar), patch.object(self.service, '_active_recognizer') as model:
                for route in ('recognize', 'recognize-many'):
                    response = client.post(f'/api/biometrics/{route}', files={'frame': ('object.png', data.tobytes(), 'image/png')})
                    self.assertEqual(response.status_code, 422, response.text)
                model.assert_not_called()
            self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original)

    def test_multiple_detections_cannot_be_hidden_by_quality_filter(self):
        detector = MagicMock()
        detector.detectMultiScale.return_value = np.array([[20, 20, 100, 100], [180, 20, 100, 100]])
        _, data = cv2.imencode('.png', np.zeros((300, 300, 3), dtype=np.uint8))
        with patch.object(self.service, 'detector', detector), patch.object(self.service, '_processed_face') as crop:
            with self.assertRaises(HTTPException) as failure:
                self.service.process_frame(data.tobytes())
            self.assertEqual(failure.exception.status_code, 422)
            crop.assert_not_called()

    def test_unverified_capture_cannot_be_saved_or_trained(self):
        frames = face_set()
        for face in frames:
            face.human_verified = False
        with self.assertRaises(HTTPException) as failure:
            self.enroll(self.first, frames)
        self.assertEqual(failure.exception.status_code, 422)
        self.assertEqual(self.samples(self.first), [])
        self.assertEqual(self.db.scalars(select(BiometricModel)).all(), [])

    def test_legacy_and_current_api_routes_reject_duplicate_enrollment(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth import current_user
        from app.database import get_db

        self.enroll(self.first, face_set())
        original_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[current_user] = lambda: self.admin
        try:
            client = TestClient(app)
            for route in (f"/api/biometrics/enroll/{self.second.id}", f"/api/biometrics/enrollments/{self.second.id}"):
                with self.subTest(route=route), patch('app.main.biometric_service', self.service), patch.object(self.service, 'process_frame', side_effect=face_set(offset=1)):
                    uploads = [('frames', (f'frame-{i}.jpg', b'frame', 'image/jpeg')) for i in range(15)]
                    response = client.post(route, data={'reason': 'Authorized enrollment'}, files=uploads)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()['detail']['code'], 'duplicate_face')
                self.assertEqual(self.samples(self.second), [])
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        TEST_DIRECTORY.cleanup()
