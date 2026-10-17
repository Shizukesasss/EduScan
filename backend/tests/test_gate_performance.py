"""Fast attendance must retain blink checks, visit boundaries, and durable events."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TEST_DIR = tempfile.TemporaryDirectory(prefix='eduscan-gate-speed-')
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['EDUSCAN_DATA_DIR'] = TEST_DIR.name
os.environ['EDUSCAN_SECRET_KEY'] = 'isolated-gate-speed-test'
os.environ['ATTENDANCE_SCHEDULER_ENABLED'] = 'false'

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import main
from app.auth import current_user
from app.database import Base, get_db
from app.models import AttendanceEvent, Person, User
from app.services.gate_presence import GatePresence
from app.services import gate_exports


class GatePerformanceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.person = Person(external_id='SPEED-1', full_name='Test Learner', role='Student', sex='Male',
                             grade='10', section='Rizal', biometric_consent=True)
        self.admin = User(username='speed-admin', full_name='Test Admin', role='admin', password_hash='unused', must_change_password=False)
        self.db.add_all([self.person, self.admin]); self.db.commit()
        self.presence = GatePresence()
        self.presence_patch = patch.object(main, 'gate_presence', self.presence)
        self.presence_patch.start()

    def tearDown(self):
        self.presence_patch.stop(); self.db.close(); self.engine.dispose()

    def match(self, live=True):
        return {'person': self.person, 'distance': 20.0, 'quality': 95, 'box': (10, 10, 100, 100),
                'presentation_verified': True, 'presentation_score': 0.99,
                'liveness_verified': live, 'message': 'Verified' if live else 'Waiting for a blink', 'review_id': None}

    def scan(self, live=True):
        tasks = BackgroundTasks()
        with patch.object(main.biometric_service, 'recognize_frames', return_value=[self.match(live)]):
            result = main.process_gate_frames(tasks, [b'frame'] * 16, 'gate-one', self.db)
        return result, tasks

    def test_attendance_is_saved_before_excel_work_runs(self):
        with patch.object(main, 'update_gate_export') as export:
            result, tasks = self.scan()
            self.assertTrue(result['results'][0]['attendance_event']['recorded'])
            self.assertEqual(result['results'][0]['attendance_event']['direction'], 'Time In')
            self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)
            export.assert_not_called()
            self.assertEqual(len(tasks.tasks), 1)
            self.assertIs(tasks.tasks[0].func, export)

    def test_continuous_presence_does_not_toggle_time_out(self):
        self.scan()
        event = self.db.scalar(select(AttendanceEvent))
        event.created_at = datetime.utcnow() - timedelta(minutes=2); self.db.commit()
        result, tasks = self.scan()
        self.assertTrue(result['results'][0]['attendance_event']['presence_hold'])
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)
        self.assertEqual(tasks.tasks, [])

    def test_departure_and_return_can_record_time_out_after_five_seconds(self):
        self.scan()
        event = self.db.scalar(select(AttendanceEvent))
        event.created_at = datetime.utcnow() - timedelta(seconds=6); self.db.commit()
        import time
        self.presence.observe('gate-one', set(), now=time.monotonic() - 3)
        result, _tasks = self.scan()
        self.assertEqual(result['results'][0]['attendance_event']['direction'], 'Time Out')
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 2)

    def test_liveness_pending_cannot_record_attendance(self):
        result, tasks = self.scan(live=False)
        self.assertFalse(result['results'][0]['attendance_event']['recorded'])
        self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])
        self.assertEqual(tasks.tasks, [])

    def test_restored_flow_records_with_legacy_blink_and_no_presentation_score(self):
        with patch.object(main.biometric_service, 'recognize_frames', return_value=[{
            **self.match(True), 'presentation_verified': None, 'presentation_score': None,
        }]):
            result = main.process_gate_frames(BackgroundTasks(), [b'frame'], 'gate-one', self.db)
        self.assertIsNone(result['results'][0]['presentation_verified'])
        self.assertTrue(result['results'][0]['attendance_event']['recorded'])
        self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)

    def test_multiple_people_record_separate_events(self):
        other = Person(external_id='SPEED-2', full_name='Other Learner', role='Student', sex='Female', biometric_consent=True)
        self.db.add(other); self.db.commit()
        with patch.object(main.biometric_service, 'recognize_frames', return_value=[self.match(), {**self.match(), 'person': other}]):
            result = main.process_gate_frames(BackgroundTasks(), [b'frame'], 'gate-one', self.db)
        self.assertEqual(result['face_count'], 2)
        self.assertTrue(all(row['attendance_event']['recorded'] for row in result['results']))
        self.assertEqual({event.person_id for event in self.db.scalars(select(AttendanceEvent)).all()}, {self.person.id, other.id})

    def test_brief_missed_detection_does_not_release_a_visit(self):
        tracker = GatePresence()
        tracker.observe('a', {1}, now=0); tracker.mark_recorded('a', 1)
        tracker.observe('a', set(), now=1); tracker.observe('a', {1}, now=2)
        self.assertTrue(tracker.already_recorded('a', 1))
        tracker.observe('b', {1}, now=2)
        self.assertFalse(tracker.already_recorded('b', 1))
        tracker.clear()
        self.assertFalse(tracker.already_recorded('a', 1))

    def test_cleared_accidental_scan_releases_only_that_person_at_all_stations(self):
        self.presence.observe('a', {1, 2}); self.presence.mark_recorded('a', 1); self.presence.mark_recorded('a', 2)
        self.presence.observe('b', {1}); self.presence.mark_recorded('b', 1)
        self.presence.forget_person(1)
        self.assertFalse(self.presence.already_recorded('a', 1))
        self.assertFalse(self.presence.already_recorded('b', 1))
        self.assertTrue(self.presence.already_recorded('a', 2))

    def test_old_single_frame_and_new_burst_api_both_work(self):
        original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.admin
        try:
            with TestClient(main.app) as client, patch.object(main.biometric_service, 'recognize_frames', return_value=[self.match(False)]) as recognize:
                # Startup uses the isolated app database; use the fixture session for requests.
                response = client.post('/api/biometrics/recognize-many', files={'frame': ('old.jpg', b'frame', 'image/jpeg')})
                self.assertEqual(response.status_code, 200, response.text)
                files = [('frames', (f'{index}.jpg', b'frame', 'image/jpeg')) for index in range(40)]
                response = client.post('/api/biometrics/recognize-many', data={'station_id': 'gate-one'}, files=files)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(recognize.call_args.args[1]), 40)
                response = client.post('/api/biometrics/recognize-many', files=files + [files[0]])
                self.assertEqual(response.status_code, 422, response.text)
        finally:
            main.app.dependency_overrides.clear(); main.app.dependency_overrides.update(original)

    def test_legacy_route_requires_liveness_and_uses_the_same_visit_rules(self):
        original = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[current_user] = lambda: self.admin
        try:
            with TestClient(main.app) as client, patch.object(main, 'update_gate_export'), \
                 patch.object(main.biometric_service, 'recognize_frames', return_value=[self.match(False)]) as recognize:
                for _ in range(3):
                    response = client.post('/api/biometrics/recognize', data={'station_id': 'legacy-test'}, files={'frame': ('face.jpg', b'face', 'image/jpeg')})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertFalse(response.json()['liveness_verified'])
                    self.assertFalse(response.json()['attendance_event']['recorded'])
                self.assertTrue(recognize.call_args.kwargs['require_single'])
                self.assertEqual(recognize.call_args.kwargs['station_id'], 'legacy-test')
                self.assertEqual(self.db.scalars(select(AttendanceEvent)).all(), [])
                recognize.return_value = [self.match(True)]
                response = client.post('/api/biometrics/recognize', data={'station_id': 'legacy-test'}, files={'frame': ('face.jpg', b'face', 'image/jpeg')})
                self.assertTrue(response.json()['attendance_event']['recorded'], response.text)
                response = client.post('/api/biometrics/recognize', data={'station_id': 'legacy-test'}, files={'frame': ('face.jpg', b'face', 'image/jpeg')})
                self.assertTrue(response.json()['attendance_event']['presence_hold'], response.text)
                self.assertEqual(len(self.db.scalars(select(AttendanceEvent)).all()), 1)
        finally:
            main.app.dependency_overrides.clear(); main.app.dependency_overrides.update(original)

    def test_export_requested_during_generation_is_not_lost(self):
        day = date(2026, 10, 12)
        def generate(_db, _day):
            if output.call_count == 1:
                gate_exports.update_gate_export(day)
        with patch.object(gate_exports, 'SessionLocal') as sessions, patch.object(gate_exports, 'generate_temporary_log', side_effect=generate) as output:
            sessions.return_value.__enter__.return_value = object()
            gate_exports.update_gate_export(day)
        self.assertEqual(output.call_count, 2)
        self.assertFalse(gate_exports._running)

    def test_fast_cooldown_is_applied_once_and_later_settings_are_preserved(self):
        from app.services.gate_defaults import configure_fast_gate
        from app.services.settings_store import get_json, set_json
        set_json(self.db, 'attendance', {'duplicate_cooldown_seconds': 45, 'absence_cutoff': '10:00', 'auto_close_enabled': False})
        self.assertTrue(configure_fast_gate(self.db))
        self.assertEqual(get_json(self.db, 'attendance', {})['duplicate_cooldown_seconds'], 5)
        self.assertEqual(get_json(self.db, 'attendance', {})['absence_cutoff'], '10:00')
        set_json(self.db, 'attendance', {'duplicate_cooldown_seconds': 20})
        self.assertFalse(configure_fast_gate(self.db))
        self.assertEqual(get_json(self.db, 'attendance', {})['duplicate_cooldown_seconds'], 20)


if __name__ == '__main__':
    try: unittest.main()
    finally: TEST_DIR.cleanup()
