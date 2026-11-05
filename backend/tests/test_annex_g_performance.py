"""Report performance checks use synthetic SQLite data and never import the API or camera."""
import os
import sys
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DATA = tempfile.TemporaryDirectory(prefix='annex-perf-', dir=ROOT / 'tmp')
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['EDUSCAN_DATA_DIR'] = DATA.name
os.environ['EDUSCAN_SECRET_KEY'] = 'isolated-annex-performance-tests'
sys.path.insert(0, str(ROOT / 'backend'))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.database import Base
from app.models import AttendanceEvent, CalendarException, Person
from app.services.annex_g import _attendance_by_learner


def test_term_attendance_has_bounded_query_count_and_preserves_placement_dates():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            person = Person(external_id='PERF-1', full_name='Synthetic Learner', role='Student',
                            sex='Female', grade='7', section='Legacy', enrollment_status='Transferred Out',
                            enrollment_end_date=date(2026, 6, 1))
            db.add(person)
            db.flush()
            db.add_all([
                AttendanceEvent(id='perf-present', person_id=person.id, event_date=date(2026, 6, 2),
                                event_time=time(7), direction='Time In', status='Present', source='Test'),
                AttendanceEvent(id='perf-absent', person_id=person.id, event_date=date(2026, 6, 3),
                                event_time=time(9), direction='Absent', status='Absent', source='Test'),
                CalendarException(id='perf-holiday', event_date=date(2026, 6, 4), event_type='Holiday',
                                  reason='Test holiday', actor_user_id=1, actor_name='Test'),
            ])
            db.commit()
            common = dict(person=person, person_id=person.id,
                          school_year=SimpleNamespace(starts_on=date(2026, 6, 1)),
                          grade_level=SimpleNamespace(name='7'), section=SimpleNamespace(name='Verified'))
            placements = [SimpleNamespace(id=1, starts_on=date(2026, 6, 2), ends_on=date(2026, 6, 5), **common),
                          SimpleNamespace(id=2, starts_on=date(2026, 6, 8), ends_on=None, **common)]
            statements = []
            def count(_conn, _cursor, statement, *_args):
                statements.append(statement)
            event.listen(engine, 'before_cursor_execute', count)
            with patch('app.services.annex_g.local_now', return_value=datetime(2026, 11, 4)):
                result = _attendance_by_learner(db, placements, date(2026, 10, 30))
            event.remove(engine, 'before_cursor_execute', count)
            assert result[1] == [{'month': '2026-06', 'days_of_class': 3, 'days_present': 1,
                                  'days_absent': 1, 'unresolved_days': 1}]
            assert result[2][0] == {'month': '2026-06', 'days_of_class': 17, 'days_present': 0,
                                     'days_absent': 0, 'unresolved_days': 17}
            assert len(statements) <= 6, f'Annex G attendance executed {len(statements)} queries'
    finally:
        engine.dispose()
