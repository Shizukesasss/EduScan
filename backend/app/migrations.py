from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .database import Base
from . import models as _models  # noqa: F401 -- register every mapped table before create_all


MIGRATIONS = (
    ("0001_initial_versioned_schema", "Create the complete versioned EduScan schema"),
    ("0002_attendance_reporting_controls", "Add learner movement fields and audited attendance-day reset"),
    ("0003_attendance_reporting_schema_repair", "Ensure attendance reporting tables and movement columns exist"),
    ("0004_section_adviser_account_link", "Link adviser authorization to a teacher account identifier"),
    ("0005_station_security_sms_controls", "Add account security and SMS idempotency controls"),
    ("0006_remove_station_direction_mode", "Remove the rejected manual scanner direction mode"),
    ("0007_personnel_attendance_schedules", "Add faculty and non-teaching duty schedules"),
    ("0008_completion_workflows", "Add reporting, grade finalization, audit, retention, SMS reconciliation, liveness review, and backup scheduling"),
    ("0009_grading_policy_engine", "Add policy-configurable gradebook engine and audit tables"),
    ("0010_subject_categories", "Add subject category column (JHS vs SHS Track)"),
    ("0011_person_name_parts", "Split person full name into surname, first_name, middle_name, and name_extension"),
    ("0012_recoverable_academic_deletion", "Allow academic setup deletion while preserving linked records"),
    ("0013_recoverable_academic_calendar_deletion", "Allow school year and grading period deletion while preserving class history"),
    ("0014_person_assignment", "Map the optional personnel assignment without changing existing values"),
    ("0015_remove_grade_level_sequence", "Remove the unused grade-level sort sequence"),
    ("0016_grade_adjustment_notifications", "Track when teachers have seen adjustment decisions"),
    ("0017_subject_teaching_assignments_and_electives", "Separate advisers from subject teachers and record elective tracks"),
    ("0018_grade_criteria_adjustment_requests", "Allow teachers to request audited grading-weight changes after finalization"),
    ("0019_enrollment_departure_notes", "Add optional lifecycle notes without changing existing records"),
    ("0020_admin_schedules_and_report_roles", "Link schedules to accounts and retain report generator roles"),
    ("0021_jhs_elective_allowed_grades", "Add compatible JHS elective grade restrictions"),
    ("0022_annual_advisers_demo_setup", "Annual adviser history and confirmed demo teacher setup"),
    ("0023_school_year_grading_reporting_mode", "Apply explicit adjusted or direct reporting by school year"),
    ("0024_replace_quarter_with_term_order", "Rename stored grading period identifiers to term order"),
    ("0025_person_date_of_birth", "Store person date of birth for calculated age"),
    ("0026_annex_g_enrollment_and_comments", "Add verified school-year learner placements and Annex G adviser comments"),
)


def _add_column_if_missing(connection, table: str, column: str, definition: str) -> None:
    columns = {item["name"] for item in inspect(connection).get_columns(table)}
    if column not in columns:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def _create_index_if_missing(connection, table: str, name: str, columns: str, unique: bool = False) -> None:
    indexes = inspect(connection).get_indexes(table)
    wanted_columns = [item.strip() for item in columns.split(",")]
    if any(item["name"] == name or (
        item.get("column_names") == wanted_columns and (not unique or item.get("unique"))
    ) for item in indexes):
        return
    qualifier = "UNIQUE " if unique else ""
    connection.execute(text(f"CREATE {qualifier}INDEX {name} ON {table} ({columns})"))


def _rename_column_if_needed(connection, table: str, old_name: str, new_name: str) -> None:
    if not inspect(connection).has_table(table):
        return
    columns = {item["name"] for item in inspect(connection).get_columns(table)}
    if old_name in columns and new_name not in columns:
        connection.execute(text(f"ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}"))


def run_migrations(engine: Engine) -> list[str]:
    """Apply idempotent, recorded schema migrations instead of untracked create_all calls."""
    applied_now: list[str] = []
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version VARCHAR(80) PRIMARY KEY, description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"
        ))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        for version, description in MIGRATIONS:
            if version in applied:
                continue
            if version == "0025_person_date_of_birth":
                _add_column_if_missing(connection, "persons", "date_of_birth", "DATE NULL")
            elif version == "0026_annex_g_enrollment_and_comments":
                Base.metadata.create_all(bind=connection)
                _add_column_if_missing(connection, "roster_import_audits", "import_mode", "VARCHAR(30) NOT NULL DEFAULT 'roster'")
                _create_index_if_missing(connection, "roster_import_audits", "ix_roster_import_audits_import_mode", "import_mode")
            elif version == "0024_replace_quarter_with_term_order":
                for table in ("grading_periods", "gradebooks", "gradebook_states", "grade_change_audits"):
                    _rename_column_if_needed(connection, table, "quarter", "term_order")
            elif version == "0023_school_year_grading_reporting_mode":
                if inspect(connection).has_table("grading_policies"):
                    _add_column_if_missing(connection, "grading_policies", "reporting_method", "VARCHAR(30) NOT NULL DEFAULT 'legacy'")
                    from .services.grading_engine import reporting_method_for_school_year
                    policies = connection.execute(text(
                        "SELECT id, school_year, version, transmutation_table_json FROM grading_policies"
                    )).all()
                    for policy_id, school_year, policy_version, table_json in policies:
                        method = reporting_method_for_school_year(school_year)
                        if method == "adjusted_2026" and (policy_version not in {
                            "Updated-Excel-3Term-v1", "MAPEH-Areas-v1", "DO015-2026-v1",
                        } or not table_json):
                            method = "legacy"
                        connection.execute(text(
                            "UPDATE grading_policies SET reporting_method=:method, "
                            "rounding_method=CASE WHEN :method='direct' THEN 'half_up' ELSE rounding_method END, "
                            "rounding_final_decimal_places=CASE WHEN :method='direct' THEN 0 ELSE rounding_final_decimal_places END "
                            "WHERE id=:id"
                        ), {"method": method, "id": policy_id})
            elif version == "0022_annual_advisers_demo_setup":
                _add_column_if_missing(connection, 'users', 'is_demo', 'BOOLEAN NOT NULL DEFAULT FALSE')
                Base.metadata.tables['section_adviser_assignments'].create(connection, checkfirst=True)
                Base.metadata.tables['demo_teacher_setup_batches'].create(connection, checkfirst=True)
                years = connection.execute(text("SELECT id FROM school_years WHERE name = '2026-2027' AND deleted_at IS NULL")).all()
                legacy = connection.execute(text('SELECT s.id, s.adviser_user_id, s.adviser_name FROM school_sections s JOIN grade_levels g ON g.id=s.grade_level_id WHERE s.deleted_at IS NULL AND s.active=TRUE AND g.deleted_at IS NULL AND g.active=TRUE AND (s.adviser_user_id IS NOT NULL OR s.adviser_name IS NOT NULL)')).all()
                if legacy and len(years) != 1:
                    raise ValueError('Cannot map existing advisers: exactly one SY 2026–2027 is required.')
                mapped_teachers = set()
                for section_id, teacher_id, teacher_name in legacy:
                    if teacher_id is None and teacher_name and teacher_name.strip():
                        teachers = connection.execute(text("SELECT id FROM users WHERE role='teacher' AND LOWER(TRIM(full_name))=:name"), {'name': teacher_name.strip().lower()}).all()
                        if len(teachers) != 1:
                            raise ValueError('Resolve the legacy adviser name before migrating annual assignments.')
                        teacher_id = teachers[0][0]
                    if teacher_id is not None:
                        if teacher_id in mapped_teachers:
                            raise ValueError('An existing adviser has multiple sections. Resolve the legacy assignments before activating annual advisers; no links were changed.')
                        mapped_teachers.add(teacher_id)
                        existing = connection.execute(text('SELECT teacher_user_id FROM section_adviser_assignments WHERE school_year_id=:year AND section_id=:section'), {'year': years[0][0], 'section': section_id}).first()
                        if existing and existing[0] != teacher_id:
                            raise ValueError('Existing annual adviser conflicts with legacy assignment.')
                        if not existing:
                            connection.execute(text('INSERT INTO section_adviser_assignments (school_year_id, section_id, teacher_user_id, created_at) VALUES (:year,:section,:teacher,:created)'), {'year': years[0][0], 'section': section_id, 'teacher': teacher_id, 'created': datetime.utcnow()})
            elif version == "0021_jhs_elective_allowed_grades":
                if inspect(connection).has_table('subjects'):
                    _add_column_if_missing(connection, 'subjects', 'allowed_grades_json', 'TEXT NULL')
            elif version == "0020_admin_schedules_and_report_roles":
                _add_column_if_missing(connection, "class_schedules", "teacher_user_id", "INTEGER NULL")
                _add_column_if_missing(connection, "generated_reports", "generated_by_role", "VARCHAR(30) NULL")
            elif version == "0019_enrollment_departure_notes":
                _add_column_if_missing(connection, "persons", "enrollment_note", "VARCHAR(1000) NULL")
            elif version == "0001_initial_versioned_schema":
                Base.metadata.create_all(bind=connection)
            elif version in {"0002_attendance_reporting_controls", "0003_attendance_reporting_schema_repair"}:
                Base.metadata.create_all(bind=connection)
                _add_column_if_missing(connection, "persons", "enrollment_status", "VARCHAR(30) NOT NULL DEFAULT 'Regular'")
                _add_column_if_missing(connection, "persons", "enrollment_start_date", "DATE NULL")
                _add_column_if_missing(connection, "persons", "enrollment_end_date", "DATE NULL")
                _add_column_if_missing(connection, "persons", "transfer_school", "VARCHAR(180) NULL")
            elif version == "0004_section_adviser_account_link":
                Base.metadata.create_all(bind=connection)
                _add_column_if_missing(connection, "school_sections", "adviser_user_id", "INTEGER NULL")
                connection.execute(text(
                    "UPDATE school_sections SET adviser_user_id = ("
                    "SELECT users.id FROM users WHERE LOWER(TRIM(users.full_name)) = LOWER(TRIM(school_sections.adviser_name)) "
                    "AND users.role = 'teacher' AND users.active = 1 LIMIT 1) "
                    "WHERE adviser_user_id IS NULL AND adviser_name IS NOT NULL"
                ))
            elif version == "0005_station_security_sms_controls":
                Base.metadata.create_all(bind=connection)
                _add_column_if_missing(connection, "users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 1")
                _add_column_if_missing(connection, "users", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
                _add_column_if_missing(connection, "users", "locked_until", "DATETIME NULL")
                _add_column_if_missing(connection, "users", "password_changed_at", "DATETIME NULL")
                _add_column_if_missing(connection, "users", "last_login_at", "DATETIME NULL")
                _add_column_if_missing(connection, "sms_outbox", "idempotency_key", "VARCHAR(160) NULL")
                _add_column_if_missing(connection, "sms_outbox", "next_attempt_at", "DATETIME NULL")
                _create_index_if_missing(connection, "sms_outbox", "uq_sms_outbox_idempotency_key",
                                         "idempotency_key", unique=True)
                _create_index_if_missing(connection, "sms_outbox", "ix_sms_outbox_next_attempt_at",
                                         "next_attempt_at")
            elif version == "0006_remove_station_direction_mode":
                connection.execute(text("DELETE FROM system_settings WHERE `key` LIKE 'scanner:mode:%'"))
            elif version == "0007_personnel_attendance_schedules":
                Base.metadata.create_all(bind=connection)
            elif version == "0008_completion_workflows":
                Base.metadata.create_all(bind=connection)
                _add_column_if_missing(connection, "class_schedules", "absence_cutoff", "TIME NULL")
                _add_column_if_missing(connection, "personnel_schedules", "absence_cutoff", "TIME NULL")
                _add_column_if_missing(connection, "grade_scores", "status", "VARCHAR(30) NOT NULL DEFAULT 'Scored'")
                _add_column_if_missing(connection, "sms_outbox", "delivered_at", "DATETIME NULL")
                _add_column_if_missing(connection, "sms_outbox", "cancelled_at", "DATETIME NULL")
                _add_column_if_missing(connection, "sms_outbox", "exhausted_at", "DATETIME NULL")
                _add_column_if_missing(connection, "sms_outbox", "gateway_status_checked_at", "DATETIME NULL")
                _create_index_if_missing(connection, "grade_scores", "ix_grade_scores_status", "status")
            elif version == "0009_grading_policy_engine":
                Base.metadata.create_all(bind=connection)
                has_policies = connection.execute(text("SELECT COUNT(*) FROM grading_policies")).scalar()
                if not has_policies:
                    from .services.grading_engine import build_default_transmutation_table
                    default_table_json = json.dumps(build_default_transmutation_table())
                    policies = [
                        {
                            "name": "DepEd Order No. 8, s. 2015 (JHS Languages/AP/EsP)",
                            "version": "1.0",
                            "description": "Standard DepEd K-12 grading policy for Languages, Araling Panlipunan, and Edukasyon sa Pagpapakatao (Grades 7-10)",
                            "school_year": "2026-2027",
                            "grade_levels": "7,8,9,10",
                            "subject_category": "Languages/AP/EsP",
                            "component_definitions_json": json.dumps([
                                {"name": "Written Work", "component_type": "Written Work", "weight": 30.0, "description": "Quizzes, unit tests, written outputs"},
                                {"name": "Performance Tasks", "component_type": "Performance Task", "weight": 50.0, "description": "Projects, presentations, oral outputs, practical demonstrations"},
                                {"name": "Quarterly Assessment", "component_type": "Quarterly Assessment", "weight": 20.0, "description": "Periodical examination"},
                            ]),
                            "transmutation_table_json": default_table_json,
                            "rounding_decimal_places": 2,
                            "rounding_final_decimal_places": 0,
                            "rounding_method": "half_up",
                            "passing_grade": 75,
                            "status": "Active",
                            "created_by_name": "System",
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                        },
                        {
                            "name": "DepEd Order No. 8, s. 2015 (JHS Math & Science)",
                            "version": "1.0",
                            "description": "Standard DepEd K-12 grading policy for Mathematics and Science (Grades 7-10)",
                            "school_year": "2026-2027",
                            "grade_levels": "7,8,9,10",
                            "subject_category": "Math/Science",
                            "component_definitions_json": json.dumps([
                                {"name": "Written Work", "component_type": "Written Work", "weight": 40.0, "description": "Quizzes, unit tests, problem sets"},
                                {"name": "Performance Tasks", "component_type": "Performance Task", "weight": 40.0, "description": "Lab experiments, projects, problem-solving demonstrations"},
                                {"name": "Quarterly Assessment", "component_type": "Quarterly Assessment", "weight": 20.0, "description": "Periodical examination"},
                            ]),
                            "transmutation_table_json": default_table_json,
                            "rounding_decimal_places": 2,
                            "rounding_final_decimal_places": 0,
                            "rounding_method": "half_up",
                            "passing_grade": 75,
                            "status": "Active",
                            "created_by_name": "System",
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                        },
                        {
                            "name": "DepEd Order No. 8, s. 2015 (JHS MAPEH & TLE)",
                            "version": "1.0",
                            "description": "Standard DepEd K-12 grading policy for MAPEH, EPP, and TLE (Grades 7-10)",
                            "school_year": "2026-2027",
                            "grade_levels": "7,8,9,10",
                            "subject_category": "MAPEH/TLE",
                            "component_definitions_json": json.dumps([
                                {"name": "Written Work", "component_type": "Written Work", "weight": 20.0, "description": "Quizzes, worksheets, written tests"},
                                {"name": "Performance Tasks", "component_type": "Performance Task", "weight": 60.0, "description": "Skills demonstration, practical performance, physical tests"},
                                {"name": "Quarterly Assessment", "component_type": "Quarterly Assessment", "weight": 20.0, "description": "Periodical examination"},
                            ]),
                            "transmutation_table_json": default_table_json,
                            "rounding_decimal_places": 2,
                            "rounding_final_decimal_places": 0,
                            "rounding_method": "half_up",
                            "passing_grade": 75,
                            "status": "Active",
                            "created_by_name": "System",
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                        },
                        {
                            "name": "General Secondary Default Policy",
                            "version": "1.0",
                            "description": "General fallback grading policy for high school subjects",
                            "school_year": "2026-2027",
                            "grade_levels": "7,8,9,10,11,12",
                            "subject_category": "General",
                            "component_definitions_json": json.dumps([
                                {"name": "Written Work", "component_type": "Written Work", "weight": 30.0, "description": "Quizzes and written outputs"},
                                {"name": "Performance Tasks", "component_type": "Performance Task", "weight": 50.0, "description": "Projects, performance tasks"},
                                {"name": "Quarterly Assessment", "component_type": "Quarterly Assessment", "weight": 20.0, "description": "Quarterly exams"},
                            ]),
                            "transmutation_table_json": default_table_json,
                            "rounding_decimal_places": 2,
                            "rounding_final_decimal_places": 0,
                            "rounding_method": "half_up",
                            "passing_grade": 75,
                            "status": "Active",
                            "created_by_name": "System",
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                        }
                    ]
                    for p in policies:
                        connection.execute(text(
                            "INSERT INTO grading_policies (name, version, description, school_year, grade_levels, "
                            "subject_category, component_definitions_json, transmutation_table_json, "
                            "rounding_decimal_places, rounding_final_decimal_places, rounding_method, passing_grade, "
                            "status, created_by_name, created_at, updated_at) VALUES ("
                            ":name, :version, :description, :school_year, :grade_levels, :subject_category, "
                            ":component_definitions_json, :transmutation_table_json, :rounding_decimal_places, "
                            ":rounding_final_decimal_places, :rounding_method, :passing_grade, :status, "
                            ":created_by_name, :created_at, :updated_at)"
                        ), p)
            elif version == "0010_subject_categories":
                _add_column_if_missing(connection, "subjects", "category", "VARCHAR(20) NOT NULL DEFAULT 'JHS'")
            elif version == "0011_person_name_parts":
                _add_column_if_missing(connection, "persons", "surname", "VARCHAR(80) NOT NULL DEFAULT ''")
                _add_column_if_missing(connection, "persons", "first_name", "VARCHAR(80) NOT NULL DEFAULT ''")
                _add_column_if_missing(connection, "persons", "middle_name", "VARCHAR(80) NULL")
                _add_column_if_missing(connection, "persons", "name_extension", "VARCHAR(20) NULL")
                
                # Backfill
                connection.execute(text("UPDATE persons SET first_name = full_name, surname = '' WHERE first_name = ''"))
            elif version == "0012_recoverable_academic_deletion":
                for table in ("grade_levels", "school_sections", "subjects"):
                    _add_column_if_missing(connection, table, "deleted_at", "TIMESTAMP NULL")
            elif version == "0013_recoverable_academic_calendar_deletion":
                for table in ("school_years", "grading_periods"):
                    _add_column_if_missing(connection, table, "deleted_at", "TIMESTAMP NULL")
            elif version == "0014_person_assignment":
                _add_column_if_missing(connection, "persons", "assignment", "VARCHAR(180) NULL")
            elif version == "0015_remove_grade_level_sequence":
                columns = {item["name"] for item in inspect(connection).get_columns("grade_levels")}
                if "sequence" in columns:
                    connection.execute(text("ALTER TABLE grade_levels DROP COLUMN sequence"))
            elif version == "0016_grade_adjustment_notifications":
                _add_column_if_missing(connection, "grade_adjustment_requests", "requester_seen_at", "TIMESTAMP NULL")
                connection.execute(text(
                    "UPDATE grade_adjustment_requests SET requester_seen_at = CURRENT_TIMESTAMP "
                    "WHERE status IN ('Approved', 'Rejected') AND requester_seen_at IS NULL"
                ))
            elif version == "0017_subject_teaching_assignments_and_electives":
                _add_column_if_missing(connection, "school_sections", "track", "VARCHAR(40) NULL")
                _add_column_if_missing(connection, "subjects", "is_elective", "BOOLEAN NOT NULL DEFAULT FALSE")
                _add_column_if_missing(connection, "subjects", "elective_track", "VARCHAR(40) NULL")
                Base.metadata.create_all(bind=connection)
            elif version == "0018_grade_criteria_adjustment_requests":
                from .models_grading import GradeCriteriaAdjustmentRequest
                GradeCriteriaAdjustmentRequest.__table__.create(bind=connection, checkfirst=True)
            connection.execute(
                text("INSERT INTO schema_migrations (version, description, applied_at) VALUES (:version, :description, :applied_at)"),
                {"version": version, "description": description, "applied_at": datetime.utcnow()},
            )
            applied_now.append(version)
    return applied_now


def upgrade_mapeh_area_schema(engine: Engine, *, approved: bool = False):
    """Explicit deployment step only; deliberately absent from startup MIGRATIONS."""
    if not approved:
        raise ValueError('Review the MAPEH impact preview and approve schema activation first.')
    if engine.dialect.name != 'postgresql':
        raise ValueError('Existing-database upgrade supports PostgreSQL; isolated SQLite uses fresh metadata.')
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE gradebooks ADD COLUMN IF NOT EXISTS learning_area VARCHAR(20) NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE gradebooks ADD COLUMN IF NOT EXISTS is_legacy_readonly BOOLEAN NOT NULL DEFAULT false"))
        constraints=inspect(conn).get_unique_constraints('gradebooks')
        old=next((c for c in constraints if c['name']=='uq_gradebook_context'),None)
        columns=['school_year_id','grading_period_id','grade_level_id','section_id','subject_id','learning_area']
        if old and old['column_names'] != columns:
            conn.execute(text('ALTER TABLE gradebooks DROP CONSTRAINT uq_gradebook_context'))
            old=None
        if not old:
            conn.execute(text('ALTER TABLE gradebooks ADD CONSTRAINT uq_gradebook_context UNIQUE (school_year_id,grading_period_id,grade_level_id,section_id,subject_id,learning_area)'))
        # These values are validated in the service and at the database boundary.
        if not any(c['name']=='ck_mapeh_area' for c in inspect(conn).get_check_constraints('gradebooks')):
            conn.execute(text("ALTER TABLE gradebooks ADD CONSTRAINT ck_mapeh_area CHECK (learning_area IN ('','music_arts','pe_health'))"))
