"""Audit, harden, or migrate the configured EduScan PostgreSQL database."""

import argparse
import os
import sys
from getpass import getpass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def show_audit(audit):
    print(f"EduScan tables found: {audit['application_tables']}")
    print(f"Effective Data API relation grants: {len(audit['data_api_grants'])}")
    print(f"EduScan relations with PUBLIC grants: {len(audit['public_grants'])}")
    for role, name in audit["data_api_grants"]:
        print(f"  {role}: {name}")
    for issue in audit["runtime_issues"]:
        print(f"  {issue}")
    if audit["missing_tables"]:
        print(f"EduScan tables missing: {', '.join(audit['missing_tables'])}")
    return int(any(audit[key] for key in ("data_api_grants", "public_grants", "runtime_issues", "missing_tables")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "revoke-data-api", "migrate"))
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.action == "revoke-data-api" and args.confirm != "REVOKE EDUSCAN DATA API GRANTS":
        parser.error("Pass --confirm \"REVOKE EDUSCAN DATA API GRANTS\" after reviewing the target.")
    supplied = os.environ.get("EDUSCAN_MIGRATION_DATABASE_URL")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import engine
    from app.migrations import run_migrations
    from app.postgres_access import audit_postgres_access, configure_postgres_access, maintenance_url, postgres_role, revoke_data_api_access

    if engine.url.get_backend_name() != "postgresql":
        parser.error("DATABASE_URL must point to PostgreSQL.")
    try:
        if args.action == "migrate":
            url = maintenance_url(engine.url, supplied or getpass("PostgreSQL maintenance URL: "))
            maintenance = create_engine(url, connect_args={"connect_timeout": 10})
            try:
                runtime_role = postgres_role(engine.url)
                applied = run_migrations(maintenance, after=lambda conn: configure_postgres_access(conn, runtime_role))
                print(f"Applied {len(applied)} migrations and synchronized application grants.")
            finally:
                maintenance.dispose()
        elif args.action == "revoke-data-api":
            with engine.begin() as conn:
                audit = revoke_data_api_access(conn)
            print("Revoked effective Data API and PUBLIC grants on EduScan tables and owned sequences.")
            show_audit(audit)
            return 0
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            return show_audit(audit_postgres_access(conn))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("PostgreSQL operation failed. Verify the selected login, connection, and object ownership.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
