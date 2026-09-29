"""
seed_demo.py - Create a clean demo database for EduScan.

Run from the backend/ directory:
    .venv\Scripts\python.exe seed_demo.py   (Windows)
    .venv/bin/python seed_demo.py           (Linux/macOS)

This wipes the existing SQLite database and re-creates it with:
  - 5 default user accounts (admin / teacher / teacher2 / records / scanner)
  - 2 school years (2026-2027 active, 2027-2028 inactive)
  - 4 grading periods per school year (Q1-Q4)
  - 6 grade levels (Grade 7-12)
  - 7 demo sections across grade levels
  - 22 subjects (JHS and SHS)
  - 3 demo class schedules (Grade 7 - Jose)
  - 2 personnel schedules
  - 15 demo students with fictional LRNs
  - 2 teacher persons
  - 2 DepEd grading policies (JHS and SHS)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/eduscan.db")
os.environ.setdefault("EDUSCAN_SECRET_KEY", "demo-seed-secret-change-before-production")
os.environ.setdefault("BIOMETRIC_ENABLED", "false")

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app import models as m  # noqa: E402, F401
from app import models_grading as mg  # noqa: E402, F401
from app.migrations import run_migrations  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "eduscan.db"


def wipe_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"[seed] Removed existing database: {DB_PATH}")


def seed(db) -> None:
    # ── Users ──────────────────────────────────────────────────────────────
    users = [
        m.User(username="admin",    password_hash=hash_password("admin123"),
               role="admin",           full_name="System Administrator", must_change_password=False),
        m.User(username="teacher",  password_hash=hash_password("teacher123"),
               role="teacher",         full_name="Juan dela Cruz",       must_change_password=False),
        m.User(username="teacher2", password_hash=hash_password("teacher123"),
               role="teacher",         full_name="Maria Santos",         must_change_password=False),
        m.User(username="records",  password_hash=hash_password("records123"),
               role="records_officer", full_name="Records Officer",      must_change_password=False),
        m.User(username="scanner",  password_hash=hash_password("scanner123"),
               role="scanner",         full_name="Gate Scanner Device",  must_change_password=False),
    ]
    db.add_all(users)
    db.flush()
    print(f"[seed] Created {len(users)} users")

    # ── School Years ────────────────────────────────────────────────────────
    sy1 = m.SchoolYear(name="2026-2027", starts_on=date(2026, 6, 1),  ends_on=date(2027, 3, 31), active=True)
    sy2 = m.SchoolYear(name="2027-2028", starts_on=date(2027, 6, 1),  ends_on=date(2028, 3, 31), active=False)
    db.add_all([sy1, sy2])
    db.flush()
    print("[seed] Created school years")

    # ── Grading Periods ─────────────────────────────────────────────────────
    quarter_dates = [
        (1, date(2026, 8,  1),  date(2026, 10, 15)),
        (2, date(2026, 10, 16), date(2026, 12, 20)),
        (3, date(2027, 1,  5),  date(2027, 3,  15)),
        (4, date(2027, 3,  16), date(2027, 3,  31)),
    ]
    periods = []
    for sy in [sy1, sy2]:
        for q, s, e in quarter_dates:
            periods.append(m.GradingPeriod(
                school_year_id=sy.id, name=f"Q{q}", quarter=q,
                starts_on=s, ends_on=e, active=(sy.id == sy1.id),
            ))
    db.add_all(periods)
    db.flush()
    print("[seed] Created grading periods")

    # ── Grade Levels ─────────────────────────────────────────────────────────
    grade_levels = []
    for i, g in enumerate(range(7, 13)):
        grade_levels.append(m.GradeLevel(name=f"Grade {g}", sequence=i + 1, active=True))
    db.add_all(grade_levels)
    db.flush()
    gl_by_name = {gl.name: gl.id for gl in grade_levels}
    print("[seed] Created grade levels")

    # ── Sections ─────────────────────────────────────────────────────────────
    adviser = users[1]
    sections_data = [
        ("Grade 7",  "Jose",       adviser.id,  adviser.full_name),
        ("Grade 7",  "Rizal",      None,        None),
        ("Grade 8",  "Mabini",     None,        None),
        ("Grade 9",  "Luna",       None,        None),
        ("Grade 10", "Bonifacio",  None,        None),
        ("Grade 11", "Berlin",     users[2].id, users[2].full_name),
        ("Grade 12", "Martin",     None,        None),
    ]
    sections = []
    for gl_name, sec_name, adv_id, adv_name in sections_data:
        sections.append(m.SchoolSection(
            grade_level_id=gl_by_name[gl_name], name=sec_name,
            adviser_name=adv_name or "", adviser_user_id=adv_id, active=True,
        ))
    db.add_all(sections)
    db.flush()
    print("[seed] Created sections")

    # ── Subjects ──────────────────────────────────────────────────────────────
    subjects_data = [
        ("AP",   "ARALING PANLIPUNAN",                         "JHS"),
        ("EsP",  "EDUKASYON SA PAGPAPAKATAO",                  "JHS"),
        ("ENG",  "ENGLISH",                                    "JHS"),
        ("FIL",  "FILIPINO",                                   "JHS"),
        ("MATH", "MATHEMATICS",                                "JHS"),
        ("SCI",  "SCIENCE",                                    "JHS"),
        ("TLE",  "TECHNOLOGY AND LIVELIHOOD EDUCATION",        "JHS"),
        ("MAPEH","MAPEH",                                      "JHS"),
        ("OC",   "Oral Communication",                         "SHS-Core"),
        ("KP",   "Komunikasyon at Pananaliksik",               "SHS-Core"),
        ("LIT",  "21st Century Literature",                    "SHS-Core"),
        ("CPA",  "Contemporary Philippine Arts",               "SHS-Core"),
        ("MIL",  "Media and Information Literacy",             "SHS-Core"),
        ("GM",   "General Mathematics",                        "SHS-Core"),
        ("STAT", "Statistics and Probability",                 "SHS-Core"),
        ("ES",   "Earth Science",                              "SHS-Core"),
        ("PR1",  "Practical Research 1",                       "SHS-Core"),
        ("ET",   "Empowerment Technologies",                   "SHS-Core"),
        ("ENTR", "Entrepreneurship",                           "SHS-Core"),
        ("PD",   "Personal Development",                       "SHS-Core"),
        ("UCSP", "Understanding Culture, Society and Politics", "SHS-Core"),
        ("PC",   "Purposive Communication",                    "SHS-Core"),
    ]
    subjects = [m.Subject(code=c, name=n, category=cat, active=True) for c, n, cat in subjects_data]
    db.add_all(subjects)
    db.flush()
    print("[seed] Created subjects")

    # ── Class Schedules ───────────────────────────────────────────────────────
    schedules = [
        m.ClassSchedule(grade="7", section="Jose", subject="ARALING PANLIPUNAN",
                        teacher_name=adviser.full_name, start_time=time(7, 30), end_time=time(8, 30)),
        m.ClassSchedule(grade="7", section="Jose", subject="ENGLISH",
                        teacher_name=adviser.full_name, start_time=time(8, 30), end_time=time(9, 30)),
        m.ClassSchedule(grade="7", section="Jose", subject="MATHEMATICS",
                        teacher_name=adviser.full_name, start_time=time(9, 30), end_time=time(10, 30)),
    ]
    db.add_all(schedules)
    db.flush()
    print("[seed] Created class schedules")

    # ── Personnel Schedules ───────────────────────────────────────────────────
    db.add_all([
        m.PersonnelSchedule(role="teacher", assignment=adviser.full_name,
                            start_time=time(7, 0), end_time=time(17, 0),
                            late_grace_minutes=15, active=True),
        m.PersonnelSchedule(role="teacher", assignment=users[2].full_name,
                            start_time=time(7, 0), end_time=time(17, 0),
                            late_grace_minutes=15, active=True),
    ])
    db.flush()
    print("[seed] Created personnel schedules")

    # ── Demo Students ─────────────────────────────────────────────────────────
    students_raw = [
        ("STU-001","100000000001","Dela Cruz", "Ana",    "Maria",   None,  "Female","7", "Jose",   "+639171111001"),
        ("STU-002","100000000002","Reyes",     "Carlo",  "Jose",    None,  "Male",  "7", "Jose",   "+639171111002"),
        ("STU-003","100000000003","Santos",    "Bianca", "Lou",     None,  "Female","7", "Jose",   "+639171111003"),
        ("STU-004","100000000004","Garcia",    "Daniel", "Rey",     None,  "Male",  "7", "Jose",   "+639171111004"),
        ("STU-005","100000000005","Torres",    "Elena",  "Grace",   None,  "Female","7", "Jose",   "+639171111005"),
        ("STU-006","100000000006","Lim",       "Felix",  "Anton",   "Jr.","Male",   "7", "Jose",   "+639171111006"),
        ("STU-007","100000000007","Cruz",      "Gina",   "Belen",   None,  "Female","7", "Jose",   "+639171111007"),
        ("STU-008","100000000008","Ramos",     "Hector", "Miguel",  None,  "Male",  "7", "Jose",   "+639171111008"),
        ("STU-009","100000000009","Flores",    "Iris",   "Cam",     None,  "Female","7", "Jose",   "+639171111009"),
        ("STU-010","100000000010","Mendoza",   "Jose",   "Martin",  None,  "Male",  "7", "Jose",   "+639171111010"),
        ("STU-011","100000000011","Rivera",    "Karla",  "Mae",     None,  "Female","10","Rizal",  "+639171111011"),
        ("STU-012","100000000012","Aquino",    "Luis",   "Pedro",   None,  "Male",  "10","Rizal",  "+639171111012"),
        ("STU-013","100000000013","Villanueva","Mia",    "Rose",    None,  "Female","11","Berlin", "+639171111013"),
        ("STU-014","100000000014","Bautista",  "Noel",   "Francis", None,  "Male",  "11","Berlin", "+639171111014"),
        ("STU-015","100000000015","Castillo",  "Olivia", "Joy",     None,  "Female","12","Martin", "+639171111015"),
    ]
    students = []
    for ext_id, lrn, sn, fn, mn, ext, sex, grade, section, phone in students_raw:
        students.append(m.Person(
            external_id=ext_id, lrn=lrn, full_name=f"{sn}, {fn} {mn}",
            surname=sn, first_name=fn, middle_name=mn, name_extension=ext,
            sex=sex, role="student", grade=grade, section=section,
            guardian_phone=phone, biometric_consent=True, active=True,
        ))
    db.add_all(students)
    db.flush()
    print(f"[seed] Created {len(students)} demo students")

    # ── Teacher Persons ───────────────────────────────────────────────────────
    db.add_all([
        m.Person(external_id="TCH-001", full_name="Juan dela Cruz",
                 surname="dela Cruz", first_name="Juan",  sex="Male",   role="teacher",
                 biometric_consent=True, active=True),
        m.Person(external_id="TCH-002", full_name="Maria Santos",
                 surname="Santos",    first_name="Maria", sex="Female", role="teacher",
                 biometric_consent=True, active=True),
    ])
    db.flush()
    print("[seed] Created teacher persons")

    # ── Grading Policies ──────────────────────────────────────────────────────
    trans = json.dumps([
        {"min": 0,  "max": 74.99, "value": 74},
        {"min": 75, "max": 79.99, "value": 75},
        {"min": 80, "max": 84.99, "value": 80},
        {"min": 85, "max": 89.99, "value": 85},
        {"min": 90, "max": 94.99, "value": 90},
        {"min": 95, "max": 100,   "value": 95},
    ])
    jhs_comp = json.dumps([
        {"name": "Written Works",        "weight": 0.30, "color": "#4f46e5", "max_items": 10},
        {"name": "Performance Tasks",    "weight": 0.50, "color": "#0891b2", "max_items": 8},
        {"name": "Quarterly Assessment", "weight": 0.20, "color": "#059669", "max_items": 1},
    ])
    shs_comp = json.dumps([
        {"name": "Written Works",        "weight": 0.25, "color": "#7c3aed", "max_items": 10},
        {"name": "Performance Tasks",    "weight": 0.50, "color": "#db2777", "max_items": 8},
        {"name": "Quarterly Assessment", "weight": 0.25, "color": "#d97706", "max_items": 1},
    ])
    db.add_all([
        mg.GradingPolicy(
            name="DepEd JHS Standard Policy", version="1.0",
            description="Standard DepEd grading policy for JHS (Grades 7-10). WW=30%, PT=50%, QA=20%.",
            school_year="2026-2027", grade_levels="7,8,9,10", subject_category="General",
            component_definitions_json=jhs_comp, transmutation_table_json=trans,
            rounding_decimal_places=2, rounding_final_decimal_places=0, rounding_method="half_up",
            passing_grade=75, status="Active", effective_date=date(2026, 6, 1),
            created_by=users[0].id, created_by_name=users[0].full_name,
        ),
        mg.GradingPolicy(
            name="DepEd SHS Standard Policy", version="1.0",
            description="Standard DepEd grading policy for SHS (Grades 11-12). WW=25%, PT=50%, QA=25%.",
            school_year="2026-2027", grade_levels="11,12", subject_category="SHS-Core",
            component_definitions_json=shs_comp, transmutation_table_json=trans,
            rounding_decimal_places=2, rounding_final_decimal_places=0, rounding_method="half_up",
            passing_grade=75, status="Active", effective_date=date(2026, 6, 1),
            created_by=users[0].id, created_by_name=users[0].full_name,
        ),
    ])
    db.flush()
    print("[seed] Created grading policies")

    db.commit()
    print("\n[seed] Demo database seeded successfully!")
    print("\n  Default login credentials:")
    print("  admin    / admin123    -> Administrator")
    print("  teacher  / teacher123  -> Teacher (Juan dela Cruz, advisory: Grade 7 - Jose)")
    print("  teacher2 / teacher123  -> Teacher (Maria Santos, advisory: Grade 11 - Berlin)")
    print("  records  / records123  -> Records Officer")
    print("  scanner  / scanner123  -> Gate Scanner Device")


if __name__ == "__main__":
    print("[seed] Starting EduScan demo database seed...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wipe_database()
    run_migrations(engine)
    db = SessionLocal()
    try:
        seed(db)
    except Exception as exc:
        db.rollback()
        print(f"[seed] ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()