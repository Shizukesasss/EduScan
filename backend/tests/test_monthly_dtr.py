from datetime import date, datetime, time
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.dialects import mysql, postgresql, sqlite

import test_attendance_sync as fixtures
from app.models import AttendanceCorrection, AttendanceEvent, Person, PersonnelSchedule, SchoolYear, User
from app.auth import create_token
from app.services.dtr import _schedule_update


def test_admin_dtr_reports_the_selected_employee_and_respects_recurring_duty():
    fixture = fixtures.AttendanceSyncTest()
    fixture.setUp()
    try:
        db, client, employee = fixture.db, fixture.client, fixture.personnel
        admin = fixture.admin_headers
        url = f'/api/dtr/{employee.id}'
        month = '?year=2024&month=2'
        db.add(PersonnelSchedule(role='Faculty', weekdays='0,1,2,3,4',
                                 start_time=time(7, 30), end_time=time(16, 30)))
        school_year = SchoolYear(name='2023-2024', starts_on=date(2023, 8, 1), ends_on=date(2024, 6, 30))
        db.add(school_year)
        db.flush()
        fixtures.set_json(db, 'school.heads', {str(school_year.id): {'full_name': 'Sample Principal'}})
        for day, hour, minute, direction in [
            (5, 7, 31, 'Time In'), (5, 11, 30, 'Time Out'),
            (6, 7, 34, 'Time In'), (6, 11, 55, 'Time Out'),
            (6, 12, 0, 'Time In'), (6, 12, 45, 'Time In'), (6, 15, 0, 'Time Out'), (6, 16, 30, 'Time Out'),
            (7, 7, 31, 'Time In'), (7, 16, 31, 'Time Out'),
            (8, 7, 30, 'Time In'), (8, 12, 0, 'Time Out'),
            (9, 12, 30, 'Time In'), (9, 16, 30, 'Time Out'),
        ]:
            db.add(AttendanceEvent(id=f'{day}-{hour}-{minute}', person_id=employee.id, event_date=date(2024, 2, day),
                                   event_time=time(hour, minute), direction=direction, status='Present'))
        db.commit()
        roster = client.get('/api/dtr/employees?role=Faculty&q=STAFF', headers=admin)
        assert roster.status_code == 200
        assert [row['id'] for row in roster.json()] == [employee.id]
        saved = client.put(f'{url}/schedule', headers=admin,
                           json=[{'weekday': 0, 'start_time': '07:30', 'end_time': '11:30'},
                                 {'weekday': 3, 'start_time': '07:30', 'end_time': '12:00'},
                                 {'weekday': 4, 'start_time': '12:30', 'end_time': '16:30'}])
        assert saved.status_code == 200, saved.text
        assert client.get(f'{url}/schedule', headers=admin).json() == saved.json()
        assert client.get(f'{url}/preview{month}', headers=fixture.teacher_headers).status_code == 403
        assert client.get(f'/api/dtr/{fixture.student.id}/preview{month}', headers=admin).status_code == 404
        preview = client.get(f'{url}/preview{month}', headers=admin)
        assert preview.status_code == 200, preview.text
        rows = preview.json()['days']
        assert len(rows) == 29
        assert rows[4]['am_departure'] == '11:30:00' and rows[4]['missing'] == []
        assert rows[4]['pm_departure'] is None
        assert rows[5]['pm_arrival'] == '12:00:00' and rows[5]['missing'] == []
        assert rows[5]['pm_departure'] == '16:30:00'
        assert rows[6]['missing'] == ['am_departure', 'pm_arrival']
        assert rows[7]['am_departure'] == '12:00:00' and rows[7]['missing'] == []
        assert rows[8]['am_arrival'] is None and rows[8]['missing'] == []
        assert (rows[6]['am_status'], rows[6]['pm_status']) == ('Present', 'Absent')
        assert (rows[8]['am_status'], rows[8]['pm_status']) == ('Not scheduled', 'Present')

        with patch.object(fixtures.reports, 'REPORT_DIR', fixtures.Path(fixtures.TEST_DIR.name)):
            xlsx = client.get(f'{url}/export{month}&format=xlsx', headers=admin)
            pdf = client.get(f'{url}/export{month}&format=pdf', headers=admin)
        assert xlsx.status_code == pdf.status_code == 200
        workbook = load_workbook(BytesIO(xlsx.content))
        sheet = workbook.active
        assert tuple(cell.value for cell in workbook['AM-PM Attendance'][8])[3::3] == ('Present', 'Absent')
        assert sheet['D8'].value == 'FEBRUARY 2024'
        assert sheet['B18'].value == sheet['J18'].value == time(7, 31)
        assert sheet['D18'].value is None
        expected_punches = [time(7, 34), time(11, 55), time(12), time(16, 30)]
        assert [cell.value for cell in sheet['B19:E19'][0]] == expected_punches
        assert [cell.value for cell in sheet['J19:M19'][0]] == expected_punches
        assert sheet['A43'].value is None
        assert sheet['A7'].value == sheet['I7'].value == 'Position: Faculty | Employee No. STAFF'
        assert sheet['B49'].value == sheet['J49'].value == 'Sample Principal'
        pages = PdfReader(BytesIO(pdf.content)).pages
        assert len(pages) >= 2
        session_text = ' '.join(page.extract_text() for page in pages[1:])
        assert all(text in session_text for text in ('AM Status', 'PM Status', 'Absent'))
        pdf_text = pages[0].extract_text()
        assert pdf_text.count('Test Staff') == pdf_text.count('Sample Principal') == 2
        assert pdf_text.count('Position: Faculty | Employee No. STAFF') == 2
        assert pdf_text.count('7:31') == 4
        assert db.query(AttendanceEvent).count() == 14
        head = User(username='head', role='school_head', full_name='School Head', password_hash='unused',
                    must_change_password=False)
        db.add(head)
        db.commit()
        head_headers = {'Authorization': f'Bearer {create_token(head)}'}
        history = client.get('/api/reports/history', headers=admin).json()
        assert len([report for report in history if report['report_type'] == 'Monthly Form 48']) == 2
        assert client.get('/api/reports/history', headers=head_headers).json() == []
        assert client.get(f"/api/reports/history/{history[0]['id']}/download", headers=head_headers).status_code == 404
    finally:
        fixture.tearDown()


def test_duty_schedule_upsert_compiles_for_supported_database_dialects():
    for dialect, upsert in [(sqlite.dialect(), 'ON CONFLICT'), (postgresql.dialect(), 'ON CONFLICT'),
                            (mysql.dialect(), 'ON DUPLICATE KEY UPDATE')]:
        sql = str(_schedule_update(dialect.name, 1, '[]').compile(dialect=dialect))
        assert 'INSERT INTO dtr_duty_schedules' in sql
        assert upsert in sql


def test_dtr_scopes_schedules_to_each_employee_and_uses_corrected_and_reset_punches():
    fixture = fixtures.AttendanceSyncTest()
    fixture.setUp()
    try:
        db, client, first = fixture.db, fixture.client, fixture.personnel
        second = Person(external_id='STAFF-2', full_name='Other Staff', role='Faculty', sex='Male')
        office = Person(external_id='OFFICE', full_name='Office Staff', role='Non-teaching Personnel', sex='Male', active=False)
        db.add_all([second, office, PersonnelSchedule(role='Faculty', weekdays='0,1,2,3,4',
                                                    start_time=time(7, 30), end_time=time(16, 30))])
        db.flush()
        day = date(2024, 2, 5)
        for person in [first, second]:
            db.add(AttendanceEvent(id=f'in-{person.id}', person_id=person.id, event_date=day,
                                   event_time=time(7, 15), direction='Time In', status='Present',
                                   created_at=datetime(2024, 2, 5, 0, 15)))
            db.add(AttendanceEvent(id=f'out-{person.id}', person_id=person.id, event_date=day,
                                   event_time=time(11, 30), direction='Time Out', status='Time Out',
                                   created_at=datetime(2024, 2, 5, 3, 30)))
        for suffix, direction, clock in [('am-out', 'Time Out', time(11, 55)),
                                         ('pm-in', 'Time In', time(12, 45)),
                                         ('pm-out', 'Time Out', time(16, 35))]:
            db.add(AttendanceEvent(id=suffix, person_id=first.id, event_date=day, event_time=clock,
                                   direction=direction, status='Present', created_at=datetime(2024, 2, 5, 5)))
        actor = fixture.admin
        db.add(AttendanceCorrection(id='corrected-time', person_id=first.id, attendance_date=day,
                                    status='Present', time_in=time(7, 30), time_out=time(16, 30),
                                    reason='Verified punch', actor_user_id=actor.id, actor_name=actor.full_name,
                                    actor_role=actor.role, before_json='{}', created_at=datetime(2024, 2, 5, 6)))
        db.commit()
        admin = fixture.admin_headers
        office_roster = client.get('/api/dtr/employees?role=Non-teaching+Personnel&q=office', headers=admin).json()
        assert office_roster[0]['id'] == office.id and not office_roster[0]['active']
        with patch.object(fixtures.reports, 'REPORT_DIR', fixtures.Path(fixtures.TEST_DIR.name)):
            file = client.get(f'/api/dtr/{office.id}/export?year=2024&month=2&format=xlsx', headers=admin)
        assert file.status_code == 200, file.text
        sheet = load_workbook(BytesIO(file.content)).active
        assert sheet['A7'].value == sheet['I7'].value == 'Position: Non-teaching Personnel | Employee No. OFFICE'
        assert client.put(f'/api/dtr/{first.id}/schedule', headers=admin,
                          json=[{'weekday': 0, 'start_time': '07:30', 'end_time': '11:30'}]).status_code == 200

        def monday(person):
            result = client.get(f'/api/dtr/{person.id}/preview?year=2024&month=2', headers=admin)
            assert result.status_code == 200, result.text
            return result.json()['days'][4]

        assert monday(first)['am_arrival'] == '07:30:00'
        assert monday(first)['am_departure'] == '11:55:00'
        assert monday(first)['pm_arrival'] == '12:45:00'
        assert monday(first)['pm_departure'] == '16:30:00'
        assert monday(first)['missing'] == []
        assert monday(second)['am_arrival'] == '07:15:00'
        assert monday(second)['missing'] == ['pm_arrival', 'pm_departure']
        assert monday(office)['review'] == 'Duty hours need review'
        with patch('app.services.attendance.datetime') as clock:
            clock.utcnow.return_value = datetime(2024, 2, 5, 7)
            fixtures.reset_day(db, day, 'Verified reset', actor)
        assert monday(first)['am_arrival'] is None
        assert monday(first)['missing'] == ['am_arrival', 'am_departure']
    finally:
        fixture.tearDown()
