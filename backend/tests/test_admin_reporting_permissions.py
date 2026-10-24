"""Real routes, temporary SQLite, synthetic learners, no live school changes."""
import hashlib
import json
import tempfile
import unittest
from datetime import date, time, datetime
from pathlib import Path
from unittest.mock import patch

import test_attendance_sync as fixtures
from sqlalchemy import select
from app import main
from app.models import AttendanceEvent, ClassSchedule, GeneratedReport, SchoolYear, Subject, User
from app.services import reports, sf2
from app.auth import create_token


class AdminReportingPermissionsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AttendanceSyncTest()
        self.fixture.setUp()
        self.db, self.client = self.fixture.db, self.fixture.client
        self.teacher, self.admin = self.fixture.teacher, self.fixture.admin
        self.admin_headers, self.teacher_headers = self.fixture.admin_headers, self.fixture.teacher_headers
        self.directory = tempfile.TemporaryDirectory(dir=fixtures.TEST_DIR.name)
        self.root = Path(self.directory.name)
        self.subject = Subject(code='TEST-MATH', name='Mathematics', category='JHS')
        self.db.add(self.subject)
        self.db.commit()
        template = Path(__file__).resolve().parents[1] / 'data/templates/School Form 2 (SF2) Daily Attendance Report of Learners.xlsx'
        self.patches = [patch.object(reports, 'REPORT_DIR', self.root), patch.object(sf2, 'EXPORT_DIR', self.root),
                        patch.object(sf2, 'template_path', return_value=template)]
        for active in self.patches:
            active.start()

    def tearDown(self):
        for active in reversed(self.patches):
            active.stop()
        self.fixture.tearDown()
        self.directory.cleanup()

    def schedule_payload(self):
        return {'grade':'10','section':'Rizal','subject':'Mathematics','teacher_name':self.teacher.full_name,
                'teacher_user_id':self.teacher.id,'weekdays':'0,1,2,3,4','start_time':'07:30','end_time':'08:30', 'absence_cutoff':'08:30'}

    def report(self, actor=None, grade='10', section='Rizal', status='Generated'):
        actor = actor or self.admin
        path = sf2.generate_sf2(self.db, 2026, 10, '10', 'Rizal', '301874', '2026-2027', 'Test School')
        item = reports.register_report(self.db, path, 'Official SF2',
            {'year':2026,'month':10,'grade':grade,'section':section,'school_year':'2026-2027'},actor)
        item.status = status
        self.db.commit()
        return item

    def test_teacher_write_generate_export_and_print_routes_are_denied(self):
        before = self.db.query(AttendanceEvent).count()
        for method, path, kwargs in [
            ('POST','/api/schedules',{'json':self.schedule_payload()}),
            ('DELETE','/api/schedules/1',{}),
            ('GET','/api/sf2/export?year=2026&month=10&grade=10&section=Rizal',{}),
            ('GET','/api/sf2/preview?year=2026&month=10&grade=10&section=Rizal',{}),
            ('GET','/api/attendance/report.xlsx?starts_on=2026-10-01&ends_on=2026-10-01',{}),
            ('GET','/api/attendance/report/print?starts_on=2026-10-01&ends_on=2026-10-01',{}),
            ('GET','/api/attendance/temporary-log?date=2026-10-01',{}),
            ('GET','/api/gradebook/example/report/print',{}),
            ('GET','/api/gradebooks/1/report/print',{}),
        ]:
            with self.subTest(path=path):
                response=self.client.request(method,path,headers=self.teacher_headers,**kwargs)
                self.assertEqual(response.status_code,403,response.text)
        self.assertEqual(self.db.query(AttendanceEvent).count(),before)
        self.assertEqual(self.db.query(GeneratedReport).count(),0)
        self.assertEqual(self.db.query(ClassSchedule).count(),0)

    def test_admin_can_create_edit_schedule_and_teacher_only_reads_own(self):
        response=self.client.post('/api/schedules',headers=self.admin_headers,json=self.schedule_payload())
        self.assertEqual(response.status_code,200,response.text)
        schedule_id=response.json()['id']
        self.db.expire_all()
        self.assertEqual(self.db.get(ClassSchedule,schedule_id).teacher_user_id,self.teacher.id)
        edited=self.client.post('/api/schedules',headers=self.admin_headers,json={**self.schedule_payload(),'id':schedule_id,'end_time':'09:00'})
        self.assertEqual(edited.status_code,200,edited.text)
        own=self.client.get('/api/schedules',headers=self.teacher_headers)
        self.assertEqual([row['id'] for row in own.json()],[schedule_id])
        other=User(username='other-teacher',full_name=self.teacher.full_name,role='teacher',active=True,password_hash='unused',must_change_password=False)
        self.db.add(other);self.db.commit()
        other_headers={'Authorization':f'Bearer {create_token(other)}'}
        self.assertEqual(self.client.get('/api/schedules',headers=other_headers).json(),[])
        self.teacher.full_name='Renamed Teacher';self.db.commit()
        self.assertEqual(len(self.client.get('/api/schedules',headers=self.teacher_headers).json()),1)

    def test_teacher_only_sees_current_admin_official_reports_for_own_classes(self):
        allowed=self.report()
        excluded=[self.report(self.teacher),self.report(section='Other'),self.report(status='Rejected'),self.report(status='Superseded')]
        legacy=self.report();legacy.generated_by_role=None;self.db.commit();excluded.append(legacy)
        result=self.client.get('/api/reports/history',headers=self.teacher_headers)
        self.assertEqual([item['id'] for item in result.json()],[allowed.id])
        for item in excluded:
            self.assertEqual(self.client.get(f'/api/reports/history/{item.id}/preview',headers=self.teacher_headers).status_code,403)
        self.assertEqual(self.client.get(f'/api/reports/history/{allowed.id}/download',headers=self.teacher_headers).status_code,403)
        self.assertEqual(self.client.post(f'/api/reports/history/{allowed.id}/review',headers=self.teacher_headers,json={'status':'Approved','note':'Not authorized'}).status_code,403)

    def test_readonly_preview_matches_registered_snapshot_and_preserves_tardy_mark(self):
        self.db.add(AttendanceEvent(id='late-fixture',person_id=self.fixture.student.id,event_date=date(2026,10,13),event_time=time(8,20),direction='Time In',status='Late',source='Test'))
        self.db.commit()
        item=self.report()
        before=Path(item.file_path).read_bytes()
        response=self.client.get(f'/api/reports/history/{item.id}/preview',headers=self.teacher_headers)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['school_id'],'301874')
        self.assertEqual(result['learners'][0]['name'],self.fixture.student.full_name.upper())
        self.assertEqual(result['learners'][0]['late'],1)
        self.assertEqual(result['learners'][0]['marks'][result['days'].index(13)],'L')
        self.assertEqual(Path(item.file_path).read_bytes(),before)
        self.assertEqual(self.db.query(AttendanceEvent).count(),1)
        self.assertEqual(self.db.query(GeneratedReport).count(),1)
        Path(item.file_path).write_bytes(before+b'tampered')
        self.assertEqual(self.client.get(f'/api/reports/history/{item.id}/preview',headers=self.teacher_headers).status_code,409)

    def test_monthly_preview_includes_departed_learners_for_the_selected_month(self):
        student=self.fixture.student
        student.enrollment_start_date=date(2026,10,1)
        student.enrollment_end_date=date(2026,10,13)
        student.enrollment_status='Dropped Out'
        student.active=False
        self.db.commit()
        october=self.client.get('/api/sf2/preview?year=2026&month=10&grade=10&section=Rizal',headers=self.admin_headers)
        self.assertEqual(october.status_code,200,october.text)
        self.assertEqual([row['person_id'] for row in october.json()['rows']],[student.id])
        september=self.client.get('/api/sf2/preview?year=2026&month=9&grade=10&section=Rizal',headers=self.admin_headers)
        self.assertEqual(september.json()['rows'],[])
        self.assertEqual(september.json()['preview_date'],'2026-09-30')

    def test_admin_can_generate_and_teacher_can_view_without_generating_another_file(self):
        response=self.client.get('/api/sf2/export?year=2026&month=10&grade=10&section=Rizal&school_id=301874&school_year=2026-2027',headers=self.admin_headers)
        self.assertEqual(response.status_code,200,response.text)
        item=self.db.scalar(select(GeneratedReport))
        self.assertEqual(item.generated_by_role,'admin')
        history=self.client.get('/api/reports/history',headers=self.teacher_headers).json()
        self.assertEqual(history[0]['id'],item.id)
        self.assertEqual(self.client.get(f'/api/reports/history/{item.id}/preview',headers=self.teacher_headers).status_code,200)
        self.assertEqual(self.db.query(GeneratedReport).count(),1)

    def test_unresolved_past_attendance_blocks_official_export_without_writing_absences(self):
        student = self.fixture.student
        student.enrollment_start_date = date(2026, 10, 1)
        self.db.commit()
        with patch.object(sf2, 'local_now', return_value=datetime(2026, 10, 18)):
            preview = self.client.get('/api/sf2/preview?year=2026&month=10&grade=10&section=Rizal', headers=self.admin_headers)
            self.assertGreater(preview.json()['unresolved_count'], 0)
            response = self.client.get('/api/sf2/export?year=2026&month=10&grade=10&section=Rizal&school_year=2026-2027', headers=self.admin_headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.db.query(AttendanceEvent).count(), 0)
        self.assertEqual(self.db.query(GeneratedReport).count(), 0)
        self.assertEqual(list(self.root.glob('*.xlsx')), [])

    def test_reporting_month_must_overlap_existing_school_year(self):
        response = self.client.get('/api/sf2/export?year=2025&month=10&grade=10&section=Rizal&school_year=2026-2027', headers=self.admin_headers)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.query(GeneratedReport).count(), 0)

    def test_daily_report_keeps_movement_separate_and_escapes_printed_values(self):
        from openpyxl import load_workbook
        student = self.fixture.student
        student.enrollment_start_date = date(2026, 10, 1)
        student.enrollment_note = '<script>unsafe</script>'
        self.db.commit()
        path = reports.generate_attendance_range_xlsx(self.db, date(2026, 10, 13), date(2026, 10, 13), 'Student', '10', 'Rizal')
        book = load_workbook(path, read_only=True)
        try:
            sheet = book['Attendance Detail']
            self.assertEqual(sheet['I4'].value, 'Attendance status')
            self.assertEqual(sheet['J4'].value, 'Enrollment / employment')
            self.assertEqual(sheet['I5'].value, 'No scan')
            self.assertEqual(sheet['J5'].value, 'Regular')
        finally:
            book.close()
        printable = reports.attendance_report_html(self.db, date(2026, 10, 13), date(2026, 10, 13), 'Student', '10', 'Rizal')
        self.assertIn('Daily Attendance and Movement', printable)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', printable)
        self.assertNotIn('<script>unsafe</script>', printable)
        self.assertEqual(self.db.query(AttendanceEvent).count(), 0)
