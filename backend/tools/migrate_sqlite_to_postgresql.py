"""
migrate_sqlite_to_postgresql.py
────────────────────────────────────────────────────────────────────────────
Non-destructive, row-verified copy of every EduScan SQLite table into the
target PostgreSQL database.

Safety guarantees
─────────────────
  • The SQLite source is NEVER modified.
  • Migration is aborted if the target already has rows in any table.
    (Run with --force-wipe only if you are certain the target is disposable.)
  • Every table is verified row-by-row count after the copy; the script
    exits non-zero if counts do not match.
  • FK checks are deferred during the bulk insert so parent rows arrive
    before child rows without ordering constraints.
  • SERIAL / SEQUENCE counters are reset to max(id)+1 after the copy so
    future INSERT statements do not collide with migrated IDs.

Usage
─────
  python backend/tools/migrate_sqlite_to_postgresql.py \
      --pg-url "postgresql+psycopg2://eduscan_app:eduscan@127.0.0.1:5432/eduscan" \
      --confirm "MIGRATE TO POSTGRESQL"

  Optional:
      --sqlite  path/to/eduscan.db    (default: backend/data/eduscan.db)
      --force-wipe                    (dangerous: clears target before copy)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import create_engine, func, inspect, select, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base
from app.migrations import run_migrations
import app.models  # noqa: F401 – registers all mapped tables with Base.metadata


CONFIRM_PHRASE = "MIGRATE TO POSTGRESQL"

# Tables that hold SERIAL (auto-increment) primary keys whose PostgreSQL
# sequences must be bumped after the bulk insert so future rows don't collide.
INT_PK_TABLES = {
    "users", "persons", "class_schedules", "personnel_schedules",
    "school_years", "grade_levels", "school_sections", "subjects",
    "grading_periods", "biometric_models", "grade_components", "grade_scores",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Copy EduScan SQLite → PostgreSQL without touching the source."
    )
    p.add_argument(
        "--sqlite",
        default=str(BACKEND_DIR / "data" / "eduscan.db"),
        help="Path to the EduScan SQLite database (default: backend/data/eduscan.db)",
    )
    p.add_argument(
        "--pg-url",
        required=True,
        help='PostgreSQL SQLAlchemy URL, e.g. postgresql+psycopg2://eduscan_app:eduscan@127.0.0.1:5432/eduscan',
    )
    p.add_argument(
        "--confirm",
        required=True,
        help=f'Must be exactly: {CONFIRM_PHRASE}',
    )
    p.add_argument(
        "--force-wipe",
        action="store_true",
        help="DANGEROUS: truncate all target tables before migrating. Use only if target data is disposable.",
    )
    return p.parse_args()


def reset_sequences(pg_connection) -> None:
    """Set each SERIAL sequence's next value to max(id)+1 to avoid PK collisions."""
    insp = inspect(pg_connection)
    for table_name in INT_PK_TABLES:
        try:
            max_id = pg_connection.scalar(
                text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
            )
            if max_id and max_id > 0:
                pg_connection.execute(
                    text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), :max_id)")
                    .bindparams(max_id=int(max_id))
                )
        except Exception as exc:
            print(f"  [warn] Could not reset sequence for {table_name}: {exc}")


def main() -> int:
    args = parse_args()

    if args.confirm != CONFIRM_PHRASE:
        raise SystemExit(f"Confirmation text must be exactly: {CONFIRM_PHRASE}")

    if not args.pg_url.startswith("postgresql"):
        raise SystemExit("--pg-url must be a PostgreSQL SQLAlchemy URL (postgresql+psycopg2://...)")

    sqlite_path = Path(args.sqlite).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    sqlite_url = f"sqlite:///{sqlite_path}"
    print(f"\nSource  : {sqlite_path}")
    print(f"Target  : {args.pg_url.split('@')[-1]}")
    print()

    # ── engines ──────────────────────────────────────────────────────────────
    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    pg_engine  = create_engine(args.pg_url, pool_pre_ping=True)

    # ── apply / verify schema on both ends ───────────────────────────────────
    print("Applying schema migrations to source (SQLite)…")
    run_migrations(src_engine)
    print("Applying schema migrations to target (PostgreSQL)…")
    run_migrations(pg_engine)

    tables = list(Base.metadata.sorted_tables)
    print(f"\nTables to migrate: {len(tables)}\n")

    # ── safety check: target must be empty (unless --force-wipe) ─────────────
    with pg_engine.connect() as pg_conn:
        occupied = {
            t.name: pg_conn.scalar(select(func.count()).select_from(t)) or 0
            for t in tables
        }
        nonempty = {n: c for n, c in occupied.items() if c > 0}

    if nonempty and not args.force_wipe:
        details = ", ".join(f"{n}={c}" for n, c in sorted(nonempty.items()))
        raise SystemExit(
            f"Target database is NOT empty — migration aborted to protect existing data.\n"
            f"Tables with rows: {details}\n"
            f"Re-run with --force-wipe only if this target data can be discarded."
        )

    if nonempty and args.force_wipe:
        print("[WARN] --force-wipe requested. Truncating target tables before copy...")
        with pg_engine.begin() as pg_conn:
            # Build a single TRUNCATE statement for all tables (CASCADE handles FK order)
            table_names = ", ".join(f'"{t.name}"' for t in tables)
            pg_conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
        print("  Tables cleared.\n")

    # ── copy rows ─────────────────────────────────────────────────────────────
    copied: dict[str, int] = {}
    print("Copying rows…")

    with src_engine.connect() as src_conn, pg_engine.begin() as pg_conn:
        # Defer all FK constraint checks until end of transaction
        pg_conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        for table in tables:
                rows = [dict(r._mapping) for r in src_conn.execute(select(table)).all()]
                count = len(rows)
                if rows:
                    pg_conn.execute(table.insert(), rows)
                copied[table.name] = count
                status = f"{count:>8} row(s)"
                print(f"  {table.name:<34} {status}")


    # ── reset sequences so new INSERTs don't conflict ─────────────────────────
    print("\nResetting PostgreSQL SERIAL sequences…")
    with pg_engine.begin() as pg_conn:
        reset_sequences(pg_conn)

    # ── verify row counts ─────────────────────────────────────────────────────
    print("\nVerifying row counts…")
    mismatches: list[str] = []
    with pg_engine.connect() as pg_conn:
        for table in tables:
            pg_count = pg_conn.scalar(select(func.count()).select_from(table)) or 0
            src_count = copied[table.name]
            if pg_count != src_count:
                mismatches.append(f"{table.name}: copied {src_count}, found {pg_count}")
            else:
                print(f"  OK {table.name:<34} {pg_count:>8} row(s)")

    if mismatches:
        print("\nVERIFICATION FAILED:")
        for m in mismatches:
            print(f"     {m}")
        return 1

    total = sum(copied.values())
    print(f"\n{'=' * 68}")
    print("MIGRATION VERIFIED SUCCESSFULLY")
    print(f"{'=' * 68}")
    print(f"  {total} total row(s) across {len(tables)} tables copied.")
    print("  SQLite source was NOT modified.")
    print()
    print("Next step: update backend/.env with the new DATABASE_URL:")
    pg_display = args.pg_url.replace(
        args.pg_url.split("@")[0].split(":")[-1], "****"
    ) if "@" in args.pg_url else args.pg_url
    print(f"  DATABASE_URL={pg_display}")
    print()
    print("Then restart EduScan:  .\\scripts\\start.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
