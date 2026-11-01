from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services.shs_section_renaming import (  # noqa: E402
    apply_rename_plan,
    build_rename_plan,
    write_manifest,
    _apply_plan,
)
from app.models import ClassSchedule, GradeComponent, GradebookState, Person, SchoolSection, SystemSetting  # noqa: E402
from app.models_grading import Gradebook  # noqa: E402


def _validate_rollback_state(db, plan: dict) -> None:
    sections = {row.id: row for row in db.query(SchoolSection).all()}
    people = {row.id: row for row in db.query(Person).all()}
    books = {row.id: row for row in db.query(Gradebook).all()}
    schedules = {row.id: row for row in db.query(ClassSchedule).all()}
    states = {row.class_key: row for row in db.query(GradebookState).all()}
    components = {row.id: row for row in db.query(GradeComponent).all()}
    settings = {row.key: row for row in db.query(SystemSetting).all()}
    for item in plan["sections"]:
        row = sections.get(item["id"])
        if row is None or row.name != item["new_name"] or row.track != item["track"] or row.track_cluster != item["cluster"]:
            raise ValueError(f"Section {item['id']} changed since the rollback manifest was created.")
    for item in plan["persons"]:
        if people.get(item["id"]) is None or people[item["id"]].section != item["new_section"]:
            raise ValueError(f"Learner {item['id']} changed since the rollback manifest was created.")
    for item in plan["gradebooks"]:
        row = books.get(item["id"])
        if row is None or row.section_name != item["new_section_name"] or row.class_key != item["new_class_key"] or row.status != item["status"]:
            raise ValueError(f"Gradebook {item['id']} changed since the rollback manifest was created.")
    for item in plan["schedules"]:
        if schedules.get(item["id"]) is None or schedules[item["id"]].section != item["new_section"]:
            raise ValueError(f"Class schedule {item['id']} changed since the rollback manifest was created.")
    for item in plan["states"]:
        row = states.get(item["new_class_key"])
        if row is None or row.section != item["new_section"]:
            raise ValueError(f"Legacy gradebook state {item['new_class_key']!r} changed since the rollback manifest was created.")
    for item in plan["components"]:
        if components.get(item["id"]) is None or components[item["id"]].class_key != item["new_class_key"]:
            raise ValueError(f"Legacy grade component {item['id']} changed since the rollback manifest was created.")
    for item in plan["settings"]:
        if settings.get(item["new_key"]) is None:
            raise ValueError(f"Legacy gradebook setting {item['new_key']!r} changed since the rollback manifest was created.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely rename tracked Grade 11–12 sections and linked labels.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the preflighted rename transaction.")
    mode.add_argument("--rollback", type=Path, help="Restore values from an applied rollback manifest.")
    parser.add_argument("--manifest", type=Path, help="Rollback manifest path for --apply.")
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            if args.rollback:
                manifest_path = args.rollback.resolve()
                if not manifest_path.is_file():
                    raise ValueError("Rollback manifest does not exist.")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("status") != "applied":
                    raise ValueError("Only an applied manifest can be rolled back.")
                plan = manifest["plan_data"]
                _validate_rollback_state(db, plan)
                db.rollback()
                with db.begin():
                    _validate_rollback_state(db, plan)
                    gradebook_ids = [row["id"] for row in plan["gradebooks"]]
                    from app.services.shs_section_renaming import _gradebook_snapshot
                    before = _gradebook_snapshot(db, gradebook_ids)
                    _apply_plan(db, plan, reverse=True)
                    db.expire_all()
                    if _gradebook_snapshot(db, gradebook_ids) != before:
                        raise ValueError("Rollback changed saved marks, calculated grades, or gradebook status.")
                write_manifest(manifest_path, plan, status="rolled_back")
                print(json.dumps({"status": "rolled_back", "manifest": str(manifest_path), "counts": plan["counts"]}, indent=2))
                return 0

            plan = build_rename_plan(db)
            if not args.apply:
                print(json.dumps({"status": "dry_run", "counts": plan["counts"], "sections": plan["sections"]}, ensure_ascii=False, indent=2))
                return 0

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            manifest_path = (args.manifest or (ROOT / "logs" / f"shs-section-renames-{timestamp}.json")).resolve()
            if not manifest_path.is_relative_to(ROOT) or manifest_path.exists():
                raise ValueError("Manifest must be a new file inside the project logs folder.")
            write_manifest(manifest_path, plan, status="prepared")
            db.rollback()
            with db.begin():
                current = build_rename_plan(db)
                if current != plan:
                    raise ValueError("Saved section references changed after preflight; no rows were updated.")
                apply_rename_plan(db, current)
            write_manifest(manifest_path, plan, status="applied")
            print(json.dumps({"status": "applied", "manifest": str(manifest_path), "counts": plan["counts"]}, indent=2))
            return 0
        except Exception as exc:
            db.rollback()
            print(f"SHS section rename stopped safely: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
