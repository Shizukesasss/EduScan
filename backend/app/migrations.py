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


def run_migrations(engine: Engine) -> list[str]:
    """Apply idempotent, recorded schema migrations instead of untracked create_all calls."""
    applied_now: list[str] = []
    with engine.begin() as connection:
        dialect = engine.dialect.name
        ts_type = "TIMESTAMP" if dialect != "sqlite" else "DATETIME"
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            f"version VARCHAR(80) PRIMARY KEY, description VARCHAR(255) NOT NULL, applied_at {ts_type} NOT NULL)"
        ))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        for version, description in MIGRATIONS:
            if version in applied:
                continue
            if version == "0001_initial_versioned_schema":
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
                active_val = "TRUE" if engine.dialect.name != "sqlite" else "1"
                connection.execute(text(
                    "UPDATE school_sections SET adviser_user_id = ("
                    "SELECT users.id FROM users WHERE LOWER(TRIM(users.full_name)) = LOWER(TRIM(school_sections.adviser_name)) "
                    f"AND users.role = 'teacher' AND users.active = {active_val} LIMIT 1) "
                    "WHERE adviser_user_id IS NULL AND adviser_name IS NOT NULL"
                ))
            elif version == "0005_station_security_sms_controls":
                Base.metadata.create_all(bind=connection)
                bool_default = "DEFAULT TRUE" if engine.dialect.name != "sqlite" else "DEFAULT 1"
                ts_type = "TIMESTAMP" if engine.dialect.name != "sqlite" else "DATETIME"
                _add_column_if_missing(connection, "users", "must_change_password", f"BOOLEAN NOT NULL {bool_default}")
                _add_column_if_missing(connection, "users", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
                _add_column_if_missing(connection, "users", "locked_until", f"{ts_type} NULL")
                _add_column_if_missing(connection, "users", "password_changed_at", f"{ts_type} NULL")
                _add_column_if_missing(connection, "users", "last_login_at", f"{ts_type} NULL")
                _add_column_if_missing(connection, "sms_outbox", "idempotency_key", "VARCHAR(160) NULL")
                _add_column_if_missing(connection, "sms_outbox", "next_attempt_at", f"{ts_type} NULL")
                _create_index_if_missing(connection, "sms_outbox", "uq_sms_outbox_idempotency_key",
                                         "idempotency_key", unique=True)
                _create_index_if_missing(connection, "sms_outbox", "ix_sms_outbox_next_attempt_at",
                                         "next_attempt_at")
            elif version == "0006_remove_station_direction_mode":
                key_col = '"key"' if engine.dialect.name != "sqlite" else "`key`"
                connection.execute(text(f"DELETE FROM system_settings WHERE {key_col} LIKE 'scanner:mode:%'"))
            elif version == "0007_personnel_attendance_schedules":
                Base.metadata.create_all(bind=connection)
            elif version == "0008_completion_workflows":
                Base.metadata.create_all(bind=connection)
                _add_column_if_missing(connection, "class_schedules", "absence_cutoff", "TIME NULL")
                _add_column_if_missing(connection, "personnel_schedules", "absence_cutoff", "TIME NULL")
                _add_column_if_missing(connection, "grade_scores", "status", "VARCHAR(30) NOT NULL DEFAULT 'Scored'")
                ts_type2 = "TIMESTAMP" if engine.dialect.name != "sqlite" else "DATETIME"
                _add_column_if_missing(connection, "sms_outbox", "delivered_at", f"{ts_type2} NULL")
                _add_column_if_missing(connection, "sms_outbox", "cancelled_at", f"{ts_type2} NULL")
                _add_column_if_missing(connection, "sms_outbox", "exhausted_at", f"{ts_type2} NULL")
                _add_column_if_missing(connection, "sms_outbox", "gateway_status_checked_at", f"{ts_type2} NULL")
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
            connection.execute(
                text("INSERT INTO schema_migrations (version, description, applied_at) VALUES (:version, :description, :applied_at)"),
                {"version": version, "description": description, "applied_at": datetime.utcnow()},
            )
            applied_now.append(version)
    return applied_now
