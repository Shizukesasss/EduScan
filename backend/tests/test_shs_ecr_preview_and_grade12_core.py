from __future__ import annotations

from types import SimpleNamespace
import unittest
from pathlib import Path

from fastapi import HTTPException
from openpyxl import load_workbook
from app.services.reports import _complete_draft_preview_record
from app.services.shs_class_record_export import (
    _course_selection,
    _normalize_cluster,
    _normalize_course,
    _normalize_text,
    _validate_template_grade_match,
)


class ShsEcrPreviewAndGrade12CoreTests(unittest.TestCase):
    def test_master_ecr_shows_track_separately_and_with_cluster_on_each_term(self) -> None:
        template = Path(__file__).resolve().parents[1] / "templates" / "SUBJECT CLASS RECORDS" / "ECR_3Term - SSHS - SY2026-2027.xlsx"
        workbook = load_workbook(template, read_only=True, data_only=False)
        try:
            self.assertEqual(workbook["INPUT DATA"]["C26"].value, "SHS TRACK")
            self.assertIn(workbook["INPUT DATA"]["F26"].value, (None, ""))
            for term in ("Term 1", "Term 2", "Term 3"):
                with self.subTest(term=term):
                    self.assertEqual(workbook[term]["Q10"].value, "SHS TRACK / CLUSTER")
                    formula = workbook[term]["U10"].value
                    self.assertTrue(formula.startswith("=IFERROR"))
                    self.assertFalse(formula.startswith("=="))
                    self.assertIn("'INPUT DATA'!F26", formula)
                    self.assertIn("HELPER!G9", formula)
                    self.assertIn(" / ", formula)
        finally:
            workbook.close()

    def test_grade12_core_uses_grade11_catalog_row_and_copies_its_helper_schedule(self) -> None:
        subject = SimpleNamespace(
            code="SHS-CORE-GM",
            name="GENERAL MATHEMATICS",
            is_elective=False,
            elective_track=None,
            elective_cluster=None,
        )
        match = {
            "track": "SSHS - CORE",
            "cluster": "CORE",
            "course": "General Mathematics",
            "grades": {11},
            "weights": {"ww": 20.0, "pt": 50.0, "exam": 30.0},
            "exam_split": {"ST1": 30.0, "ST2": 30.0, "TE": 40.0},
            "term_counts": {11: 3, 12: 0},
            "helper_row": 8,
            "grade11_helper": {"N": "11 ", "P": 3, "Q": 2, "R": 6},
        }
        catalog = {
            (_normalize_text("SSHS - CORE"), _normalize_cluster("CORE"), _normalize_course("General Mathematics")): [match]
        }

        selection = _course_selection(subject, "12", catalog)

        self.assertEqual(selection[2], "General Mathematics")
        self.assertEqual(selection[5], 3)
        self.assertEqual(selection[7], {"N8": "11 12", "S8": 12, "T8": 3, "U8": 2, "V8": 6})

    def test_grade12_elective_does_not_inherit_grade11_core_entry(self) -> None:
        subject = SimpleNamespace(
            code="SHS-TP-AWHC-01",
            name="AESTHETIC SERVICES (BEAUTY CARE)",
            is_elective=True,
            elective_track="Technical Professional (TechPro) Track",
            elective_cluster="Aesthetic, Wellness, and Human Care",
        )
        catalog = {
            (_normalize_text("SSHS - TECHPRO"), _normalize_cluster(subject.elective_cluster), _normalize_course(subject.name)): [
                {
                    "track": "SSHS - TECHPRO",
                    "cluster": subject.elective_cluster,
                    "course": subject.name,
                    "grades": {11},
                    "weights": {"ww": 15.0, "pt": 65.0, "exam": 20.0},
                    "exam_split": {"ST1": 30.0, "ST2": 30.0, "TE": 40.0},
                    "term_counts": {11: 3, 12: 0},
                    "helper_row": 120,
                    "grade11_helper": {"N": "11 ", "P": 3, "Q": 2, "R": 6},
                }
            ]
        }

        with self.assertRaisesRegex(HTTPException, "does not list"):
            _course_selection(subject, "12", catalog)

    def test_ecr_track_value_uses_the_saved_supported_shs_track(self) -> None:
        from app.services import shs_class_record_export

        track_value = getattr(shs_class_record_export, "_section_track_for_export", None)
        self.assertTrue(callable(track_value), "ECR exporter should expose the saved SHS track")
        for track in ("Academic Track", "Technical Professional (TechPro) Track"):
            with self.subTest(track=track):
                self.assertEqual(track_value({"gradebook": {"section_track": track}}), track)

        with self.assertRaisesRegex(HTTPException, "supported SHS track"):
            track_value({"gradebook": {"section_track": "Other Track"}})

    def test_only_complete_draft_records_can_be_previewed(self) -> None:
        complete_draft = {
            "gradebook": {"status": "Draft"},
            "students": [{"person_id": 1}],
            "statistics": {"incomplete": 0},
        }
        incomplete_draft = {**complete_draft, "statistics": {"incomplete": 1}}
        finalized = {**complete_draft, "gradebook": {"status": "Finalized"}}
        no_students = {**complete_draft, "students": []}

        self.assertTrue(_complete_draft_preview_record(complete_draft))
        self.assertFalse(_complete_draft_preview_record(incomplete_draft))
        self.assertFalse(_complete_draft_preview_record(finalized))
        self.assertFalse(_complete_draft_preview_record(no_students))

    def test_export_allows_only_one_hundredth_initial_grade_rounding_difference(self) -> None:
        self.assertTrue(_validate_template_grade_match(82.41, 89, 82.40, 89, draft_preview=True))
        self.assertTrue(_validate_template_grade_match(82.41, 89, 82.40, 89, draft_preview=False))
        self.assertFalse(_validate_template_grade_match(82.40, 89, 82.40, 89, draft_preview=True))
        with self.assertRaises(HTTPException):
            _validate_template_grade_match(82.42, 89, 82.40, 89, draft_preview=True)
        with self.assertRaises(HTTPException):
            _validate_template_grade_match(82.42, 89, 82.40, 89, draft_preview=False)
        with self.assertRaises(HTTPException):
            _validate_template_grade_match(82.41, 89, 82.40, 88, draft_preview=True)


if __name__ == "__main__":
    unittest.main()
