"""Enable sync in the Windows launcher with the school's verified PostgreSQL connection."""

import argparse
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def write_station_url(path: Path, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    setting = "EDUSCAN_SYNC_DATABASE_URL"
    lines = [line for line in lines if line.partition("=")[0].strip() != setting]
    lines.append(f"{setting}={value}")
    temporary = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    with temporary:
        temporary_path = Path(temporary.name)
    try:
        temporary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca", type=Path, required=True, help="School database provider's trusted PEM certificate bundle")
    parser.add_argument("--check", action="store_true", help="Verify prerequisites without changing the station configuration")
    args = parser.parse_args()
    if not args.ca.is_file():
        parser.error("The CA certificate bundle does not exist.")

    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    from app.database import engine
    from app.migrations import MIGRATIONS
    from app.postgres_access import audit_postgres_access

    if engine.url.get_backend_name() != "postgresql":
        parser.error("Configure DATABASE_URL with the school's restricted PostgreSQL login first.")
    sync_url = engine.url.update_query_dict({
        "sslmode": "verify-full", "sslrootcert": args.ca.resolve().as_posix(),
    })
    remote = create_engine(sync_url, hide_parameters=True, connect_args={"connect_timeout": 8})
    try:
        with remote.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            audit = audit_postgres_access(conn)
            if any(audit[key] for key in ("data_api_grants", "public_grants", "runtime_issues", "missing_tables")):
                print("The school database must pass the EduScan migration and access audit before enabling sync.", file=sys.stderr)
                return 1
            applied = set(conn.scalars(text("SELECT version FROM public.schema_migrations")))
            if any(version not in applied for version, _ in MIGRATIONS):
                print("The school database has pending migrations.", file=sys.stderr)
                return 1
    except SQLAlchemyError:
        print("Could not verify the school database connection. Check the CA bundle, hostname, and runtime login.", file=sys.stderr)
        return 1
    finally:
        remote.dispose()
        engine.dispose()

    if not args.check:
        write_station_url(backend / ".env", sync_url.render_as_string(hide_password=False))
    print("Station sync prerequisites verified." if args.check else "Station sync configured for the offline launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
