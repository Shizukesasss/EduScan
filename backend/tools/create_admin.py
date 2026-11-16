"""Run from backend to provision a named administrator from the server console."""

from __future__ import annotations

import argparse
import sys
from getpass import getpass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import hash_password
from app.database import SessionLocal, engine
from app.migrations import initialize_database
from app.models import User
from app.schemas import UserCreate


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a named EduScan administrator in the configured database.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()

    password = getpass("Temporary password: ")
    if password != getpass("Repeat temporary password: "):
        parser.error("The passwords do not match.")
    try:
        account = UserCreate(username=args.username.strip().lower(), full_name=args.full_name.strip(),
                             role="admin", password=password)
    except ValidationError as error:
        parser.error(". ".join(item["msg"] for item in error.errors(include_input=False)))

    initialize_database(engine)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(func.lower(User.username) == account.username)) is not None:
            parser.error("An account with that username already exists.")
        db.add(User(username=account.username, full_name=account.full_name, role=account.role,
                    password_hash=hash_password(account.password), active=True, must_change_password=True))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            parser.error("Could not create the account because it conflicts with an existing record.")
    print(f"Created administrator '{account.username}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
