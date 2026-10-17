"""Apply the user-approved template policies without changing any score row."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DATA_DIR, settings
from app.database import SessionLocal
from app.models import SchoolYear, Subject, User
from app.models_grading import AssessmentItem, Gradebook, GradebookComponent, GradingPolicy, StudentScore
from app.services.academic_context import is_junior_high
from app.services.template_policies import align_open_gradebook, ensure_template_policies


def rows(db, model):
    return [{column.name: getattr(record, column.name) for column in model.__table__.columns}
            for record in db.scalars(select(model).order_by(model.id)).all()]


def fingerprint(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, default=str).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with SessionLocal() as db:
        years = db.scalars(select(SchoolYear).where(SchoolYear.active.is_(True), SchoolYear.deleted_at.is_(None)).with_for_update()).all()
        books = db.scalars(select(Gradebook).where(
            Gradebook.school_year_id.in_([year.id for year in years]), Gradebook.subject.has(Subject.deleted_at.is_(None)),
            Gradebook.grade_level.has(deleted_at=None), Gradebook.section.has(deleted_at=None),
            Gradebook.grading_period.has(deleted_at=None)).order_by(Gradebook.id).with_for_update()).all()
        books = [book for book in books if is_junior_high(book.grade_name)]
        print(json.dumps({'active_years': [year.name for year in years],
                          'records': [(book.id, book.subject_name, book.status) for book in books]}))
        if not args.apply:
            return
        if any(book.status in {'Finalized', 'Locked'} for book in books):
            raise RuntimeError('A finalized record requires explicit teacher reopening; nothing was changed.')
        actor = db.scalar(select(User).where(User.role == 'admin', User.active.is_(True)).order_by(User.id))
        if actor is None:
            raise RuntimeError('No active administrator exists for the maintenance audit.')
        snapshot = {model.__tablename__: rows(db, model) for model in
                    (GradingPolicy, Gradebook, GradebookComponent, AssessmentItem, StudentScore)}
        before_hash = fingerprint(snapshot['student_scores'])
        maximums = {row['id']: row['max_score'] for row in snapshot['assessment_items']}
        backup = DATA_DIR / 'backups' / f'template-policy-before-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json.enc'
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open('xb') as file:
            file.write(Fernet(settings.encryption_key).encrypt(json.dumps(snapshot, default=str).encode()))
        policies = {year.id: ensure_template_policies(db, year.name, actor) for year in years}
        for book in books:
            align_open_gradebook(db, book, actor, policies[book.school_year_id])
        assert before_hash == fingerprint(rows(db, StudentScore)), 'Saved score rows changed; transaction will roll back.'
        for item in db.scalars(select(AssessmentItem)).all():
            if item.id in maximums:
                assert item.max_score == maximums[item.id], 'An existing assessment maximum changed; rolling back.'
        db.commit()
        assert before_hash == fingerprint(rows(db, StudentScore)), 'Post-commit score verification failed.'
        print(json.dumps({'aligned_records': len(books), 'policies_per_year': 4,
                          'score_rows_preserved': len(snapshot['student_scores']), 'score_sha256': before_hash,
                          'encrypted_backup': str(backup)}))


if __name__ == '__main__':
    main()
