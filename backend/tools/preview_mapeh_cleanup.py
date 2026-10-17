"""Read-only replacement for the old one-off MAPEH deletion scripts."""
import argparse
import os
import sys
from pathlib import Path


def main(subsubjects: bool = False) -> int:
    parser = argparse.ArgumentParser(description="Preview old MAPEH records. This tool never deletes data; use the audited administration workflow for changes.")
    parser.add_argument("--database-url", default=os.getenv("EDUSCAN_MAINTENANCE_DATABASE_URL"), help="Explicit target, or set EDUSCAN_MAINTENANCE_DATABASE_URL")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("An explicit database target is required")
    # Do not import app configuration, create runtime files, or open its default database.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import create_engine, text
    engine = create_engine(args.database_url)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            elif engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only=ON")
            elif engine.dialect.name == "mysql":
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            rows = connection.execute(text(
                "SELECT id, subject_name FROM gradebooks WHERE subject_name LIKE :name"
                if subsubjects else
                "SELECT g.id, g.subject_name FROM gradebooks g JOIN subjects s ON s.id = g.subject_id WHERE s.name = :name"
            ), {"name": "MAPEH - %" if subsubjects else "MAPEH"}).all()
            print(f"Read-only preview: {len(rows)} matching gradebooks. No records were changed.")
            for row in rows:
                print(f"Gradebook {row.id}: {row.subject_name}")
            connection.rollback()
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
