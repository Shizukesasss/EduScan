"""Run from backend: python tools/link_google_account.py --username admin --email head@deped.gov.ph"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, engine
from app.migrations import run_migrations
from app.services.google_login import reserve_google_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Reserve an existing EduScan account for a DepEd email. Google verifies ownership at first sign-in.")
    parser.add_argument("--username", required=True, help="Existing EduScan username; its role and assignments are preserved")
    parser.add_argument("--email", required=True, help="Exact school-authorized @deped.gov.ph address")
    args = parser.parse_args()
    run_migrations(engine)
    with SessionLocal() as db:
        try:
            user = reserve_google_email(db, args.username, args.email)
        except ValueError as error:
            parser.error(str(error))
        print(f"Reserved {user.google_email} for {user.username} ({user.role}). Ownership will be verified by Google at first sign-in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
