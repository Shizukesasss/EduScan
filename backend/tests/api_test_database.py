"""Bind the cached API application to one integration test's disposable storage."""

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event


@contextmanager
def isolated_app_database(database_path: Path, data_dir: Path, sf2_template_path: str = ""):
    import app.config as config
    import app.database as database
    import app.main as main
    from app.services import backup, biometrics, reports, retention, sf2

    database_path.parent.mkdir(parents=True, exist_ok=True)
    biometric_dir = data_dir / "biometrics"
    model_dir = data_dir / "models"
    template_dir = data_dir / "templates"
    export_dir = data_dir / "exports"
    report_dir = export_dir / "registered"
    for directory in (biometric_dir, model_dir, template_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    (data_dir / ".encryption_key").write_bytes(config.settings.encryption_key)

    test_engine = create_engine(f"sqlite:///{database_path.as_posix()}",
                                connect_args={"check_same_thread": False}, pool_pre_ping=True)
    @event.listens_for(test_engine, "connect")
    def configure_sqlite(connection, _connection_record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
    original_engine = database.engine
    database.SessionLocal.configure(bind=test_engine)
    try:
        with ExitStack() as stack:
            for module, name, value in (
                (database, "engine", test_engine), (main, "engine", test_engine),
                (backup, "engine", test_engine),
                (config, "DATA_DIR", data_dir), (config, "BIOMETRIC_DIR", biometric_dir),
                (config, "MODEL_DIR", model_dir), (config, "TEMPLATE_DIR", template_dir),
                (config, "EXPORT_DIR", export_dir),
                (backup, "DATA_DIR", data_dir), (backup, "BIOMETRIC_DIR", biometric_dir),
                (backup, "MODEL_DIR", model_dir), (backup, "TEMPLATE_DIR", template_dir),
                (backup, "BACKUP_DIR", data_dir / "backups"),
                (backup, "PENDING_DIR", data_dir / "pending_restore"),
                (main, "BACKUP_DIR", data_dir / "backups"),
                (biometrics, "BIOMETRIC_DIR", biometric_dir),
                (biometrics, "MODEL_DIR", model_dir),
                (reports, "EXPORT_DIR", export_dir), (reports, "REPORT_DIR", report_dir),
                (main, "REPORT_DIR", report_dir),
                (retention, "BIOMETRIC_DIR", biometric_dir),
                (retention, "MODEL_DIR", model_dir),
                (sf2, "EXPORT_DIR", export_dir), (sf2, "TEMPLATE_DIR", template_dir),
                (sf2, "DEFAULT_TEMPLATE", template_dir / "School Form 2 (SF2) Daily Attendance Report of Learners.xlsx"),
                (sf2, "settings", replace(sf2.settings, sf2_template_path=sf2_template_path)),
            ):
                stack.enter_context(patch.object(module, name, value))
            yield
    finally:
        database.SessionLocal.configure(bind=original_engine)
        test_engine.dispose()
