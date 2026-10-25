from __future__ import annotations

import io
import unittest
from datetime import date, timedelta

from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from pydantic import ValidationError

from app import main
from app.database import Base
from app.models import GradeLevel, Person, SchoolSection, User
from app.schemas import PersonCreate
from app.services.attendance import local_now
from app.services.roster import import_roster, parse_roster


class PersonDateOfBirthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = User(username="dob-admin", password_hash="test", role="admin", full_name="Test Administrator")
        self.db.add(self.admin)
        grade = GradeLevel(name="7")
        self.db.add(grade)
        self.db.flush()
        self.db.add(SchoolSection(grade_level_id=grade.id, name="Jose"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def payload(self, **changes):
        return PersonCreate(**{
            "external_id": "DOB-STUDENT",
            "first_name": "Test",
            "surname": "Learner",
            "sex": "Female",
            "role": "Student",
            "grade": "7",
            "section": "Jose",
            **changes,
        })

    def test_new_student_creation_requires_date_of_birth(self):
        with self.assertRaises(HTTPException) as failure:
            main._new_person_record(self.payload(), self.db, self.admin)

        self.assertEqual(failure.exception.status_code, 422)
        self.assertEqual(self.db.scalar(select(func.count(Person.id))), 0)

    def test_staff_creation_can_omit_date_of_birth(self):
        payload = PersonCreate(
            external_id="EMP-NO-DOB", first_name="Staff", surname="Test",
            sex="Female", role="Faculty",
        )

        person = main._new_person_record(payload, self.db, self.admin)

        self.assertIsNone(person.date_of_birth)

    def test_admin_create_and_roster_responses_include_birth_date(self):
        person = main.create_person(self.payload(date_of_birth="2011-02-12"), self.db, self.admin)
        self.assertEqual(person["date_of_birth"], date(2011, 2, 12))

        listed = main.admin_persons(self.db, self.admin)
        self.assertEqual(
            next(item for item in listed if item["external_id"] == "DOB-STUDENT")["date_of_birth"],
            date(2011, 2, 12),
        )

    def test_generic_person_serialization_hides_birth_date_by_default(self):
        person = main.create_person(self.payload(date_of_birth="2011-02-12"), self.db, self.admin)
        stored_person = self.db.get(Person, person["id"])

        public = main.person_json(stored_person, self.db)
        admin = main.person_json(stored_person, self.db, include_sensitive=True)

        self.assertNotIn("date_of_birth", public)
        self.assertEqual(admin["date_of_birth"], date(2011, 2, 12))

    def test_non_admin_audit_response_hides_birth_date(self):
        records_officer = User(
            username="dob-records", password_hash="test", role="records_officer",
            full_name="Test Records Officer",
        )
        self.db.add(records_officer)
        self.db.commit()
        person = main.create_person(self.payload(date_of_birth="2011-02-12"), self.db, self.admin)

        restricted = main.system_audit(None, None, 500, self.db, records_officer)
        administrator = main.system_audit(None, None, 500, self.db, self.admin)
        restricted_event = next(item for item in restricted if item["entity_id"] == str(person["id"]))
        administrator_event = next(item for item in administrator if item["entity_id"] == str(person["id"]))

        self.assertNotIn("date_of_birth", restricted_event["after"])
        self.assertEqual(administrator_event["after"]["date_of_birth"], "2011-02-12")

    def test_future_date_of_birth_is_rejected_using_manila_date(self):
        tomorrow = local_now().date() + timedelta(days=1)

        with self.assertRaises(ValidationError):
            self.payload(date_of_birth=tomorrow.isoformat())

    def test_legacy_student_without_birth_date_remains_editable(self):
        person = Person(
            external_id="LEGACY-STUDENT", full_name="Learner, Test", surname="Learner",
            first_name="Test", sex="Female", role="Student", grade="7", section="Jose",
        )
        self.db.add(person)
        self.db.commit()
        payload = self.payload(external_id="LEGACY-STUDENT")

        result = main.update_person(person.id, payload, self.db, self.admin)

        self.assertEqual(result["id"], person.id)
        self.assertIsNone(self.db.get(Person, person.id).date_of_birth)

    def test_converting_staff_record_to_student_requires_birth_date(self):
        person = Person(
            external_id="STAFF-TO-STUDENT", full_name="Staff, Test", surname="Staff",
            first_name="Test", sex="Female", role="Faculty",
        )
        self.db.add(person)
        self.db.commit()

        with self.assertRaises(HTTPException) as failure:
            main.update_person(person.id, self.payload(external_id="STAFF-TO-STUDENT"), self.db, self.admin)

        self.assertEqual(failure.exception.status_code, 422)
        self.assertEqual(self.db.get(Person, person.id).role, "Faculty")

    def workbook(self, headers, *rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def test_roster_parses_excel_date_and_iso_birth_dates(self):
        rows, errors = parse_roster(self.workbook(
            ["External ID", "Full Name", "Sex", "Role", "Grade", "Section", "DOB"],
            ["DOB-EXCEL", "Excel Learner", "Female", "Student", "7", "Jose", date(2012, 4, 5)],
            ["DOB-ISO", "ISO Learner", "Male", "Student", "7", "Jose", "2013-06-07"],
        ))

        self.assertFalse(errors)
        self.assertEqual([row["date_of_birth"] for row in rows], [date(2012, 4, 5), date(2013, 6, 7)])

    def test_roster_rejects_invalid_birth_date(self):
        rows, errors = parse_roster(self.workbook(
            ["External ID", "Full Name", "Sex", "Role", "Grade", "Section", "Date of Birth"],
            ["DOB-INVALID", "Invalid Learner", "Female", "Student", "7", "Jose", "not a date"],
        ))

        self.assertFalse(rows)
        self.assertEqual(errors[0]["row"], 2)
        self.assertIn("date of birth", errors[0]["errors"][0])

    def test_new_student_roster_row_requires_birth_date(self):
        data = self.workbook(
            ["External ID", "Full Name", "Sex", "Role", "Grade", "Section", "Date of Birth"],
            ["DOB-MISSING", "Missing Learner", "Female", "Student", "7", "Jose", None],
        )

        preview = import_roster(self.db, data, "roster.xlsx", "Approved test", self.admin, True)

        self.assertEqual(preview["valid_rows"], 0)
        self.assertEqual(preview["invalid_rows"], 1)
        self.assertIn("date of birth is required", " ".join(preview["errors"][0]["errors"]).lower())
        with self.assertRaises(HTTPException):
            import_roster(self.db, data, "roster.xlsx", "Approved test", self.admin, False)
        self.assertIsNone(self.db.scalar(select(Person).where(Person.external_id == "DOB-MISSING")))

    def test_blank_birth_date_on_roster_update_preserves_verified_value(self):
        main.create_person(self.payload(date_of_birth="2011-02-12"), self.db, self.admin)
        data = self.workbook(
            ["External ID", "Full Name", "Sex", "Role", "Grade", "Section", "Date of Birth"],
            ["DOB-STUDENT", "Updated Learner", "Female", "Student", "7", "Jose", None],
        )

        result = import_roster(self.db, data, "roster.xlsx", "Approved test", self.admin, False)

        updated = self.db.scalar(select(Person).where(Person.external_id == "DOB-STUDENT"))
        self.assertEqual(result["updated"], 1)
        self.assertEqual(updated.date_of_birth, date(2011, 2, 12))

    def test_staff_roster_can_omit_birth_date(self):
        data = self.workbook(
            ["External ID", "Full Name", "Sex", "Role", "Assignment"],
            ["DOB-STAFF", "Staff Member", "Female", "Faculty", "Science"],
        )

        rows, errors = parse_roster(data)

        self.assertFalse(errors)
        self.assertIsNone(rows[0].get("date_of_birth"))


if __name__ == "__main__":
    unittest.main()
