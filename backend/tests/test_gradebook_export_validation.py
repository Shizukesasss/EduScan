from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services import shs_class_record_export
from app.services import reports

try:
    gradebook_validation = import_module("app.services.gradebook_validation")
except ModuleNotFoundError:
    gradebook_validation = None


class GradebookExportValidationTests(unittest.TestCase):
    def test_common_export_preflight_groups_school_status_and_per_learner_score_blockers(self) -> None:
        collect_issues = getattr(gradebook_validation, "collect_common_export_issues", None)
        self.assertTrue(callable(collect_issues), "common read-only export validation must exist")

        full = {
            "gradebook": {"status": "Draft", "teacher_name": "", "section_name": "Malaya"},
            "students": [{
                "person_id": 7,
                "full_name": "Ada Cruz",
                "scores": {"10": 21},
                "score_statuses": {"10": "Scored"},
            }, {
                "person_id": 8,
                "full_name": "Ben Santos",
                "scores": {"10": 18},
                "score_statuses": {"10": "Excused"},
            }],
            "components": [{
                "id": 3,
                "name": "Written Works",
                "weight": 100,
                "items": [{"id": 10, "label": "Quiz 1", "max_score": 20, "active": True}],
            }],
        }

        issues = collect_issues(full, "", "", "ABC")
        codes = {issue["code"] for issue in issues}
        self.assertTrue({
            "SCHOOL_REGION_REQUIRED", "SCHOOL_DIVISION_REQUIRED", "SCHOOL_ID_INVALID",
            "GRADEBOOK_NOT_FINALIZED", "GRADEBOOK_TEACHER_MISSING", "SCORE_INVALID",
        }.issubset(codes))
        score_issue = next(issue for issue in issues if issue["code"] == "SCORE_INVALID")
        self.assertEqual(score_issue["location"], {
            "type": "learner_activity", "learnerId": 7, "learnerName": "Ada Cruz", "activityName": "Quiz 1",
        })
        self.assertIn("0 to 20", score_issue["correction"])
        self.assertEqual(score_issue["blocks"], ["finalization", "export"])
        status_issue = next(issue for issue in issues if issue["code"] == "SCORE_MISSING" and issue["location"]["learnerId"] == 8)
        self.assertIn("status from Excused to Scored", status_issue["correction"])

    def test_adaptive_shs_preflight_names_unsupported_track_and_missing_elective_cluster(self) -> None:
        collect_issues = getattr(gradebook_validation, "collect_common_export_issues", None)
        self.assertTrue(callable(collect_issues), "common read-only export validation must exist")
        full = {
            "gradebook": {
                "grade_name": "Grade 12", "section_name": "Malaya", "section_track": "Legacy Track",
                "subject_name": "Research 1", "subject_is_elective": True, "subject_elective_cluster": "",
                "status": "Finalized", "teacher_name": "Geo Ong",
            },
            "students": [{"person_id": 1, "full_name": "Ada Cruz"}],
            "components": [],
        }

        issues = collect_issues(full, "V", "Division", "301874")
        by_code = {issue["code"]: issue for issue in issues}
        self.assertEqual(by_code["SHS_TRACK_UNSUPPORTED"]["location"], {
            "type": "section", "sectionName": "Malaya", "field": "SHS track",
        })
        self.assertEqual(by_code["SHS_ELECTIVE_CLUSTER_MISSING"]["location"], {
            "type": "subject", "subjectName": "Research 1", "field": "Elective cluster",
        })

    def test_report_preflight_dispatch_is_read_only_and_returns_actionable_issues(self) -> None:
        full = {
            "gradebook": {
                "grade_name": "Grade 9", "subject_name": "Physics", "school_year_name": "2026-2027",
                "section_name": "Malaya", "status": "Draft", "teacher_name": "Jaekob Baroma", "term_order": 1,
            },
            "policy": {"rounding_method": "half_up", "rounding_decimal_places": 2},
            "components": [], "students": [],
        }
        book = SimpleNamespace(id=11, teacher_user_id=4, subject=SimpleNamespace(is_elective=False))
        db = SimpleNamespace(get=lambda model, key: book)

        with patch("app.services.grading.get_gradebook_full", return_value=full), \
                patch.object(reports, "new_report_path", side_effect=AssertionError("preflight must not write an XLSX")):
            issues = reports.validate_gradebook_report_xlsx(db, 11, "", "", "ABC")

        codes = {issue["code"] for issue in issues}
        self.assertTrue({
            "SCHOOL_REGION_REQUIRED", "SCHOOL_DIVISION_REQUIRED", "SCHOOL_ID_INVALID",
            "GRADEBOOK_NOT_FINALIZED", "NO_ACTIVE_LEARNERS", "ASSESSMENT_COMPONENTS_MISSING",
        }.issubset(codes))
        self.assertTrue(all(issue["group"] and issue["correction"] and issue["location"] for issue in issues))

    def test_ecr_grade_calculation_reports_every_mismatched_learner_with_saved_and_ecr_values(self) -> None:
        self.assertIsNotNone(gradebook_validation, "gradebook validation helpers must exist")
        collect_issues = getattr(gradebook_validation, "collect_grade_calculation_issues", None)
        self.assertTrue(callable(collect_issues), "grade calculation mismatch collector must exist")

        students = [
            {"person_id": 1, "full_name": "Ada Cruz", "initial_grade": 82.42, "reported_grade": 90},
            {"person_id": 2, "full_name": "Ben Santos", "initial_grade": 77.20, "reported_grade": 81},
        ]
        calculated = {
            1: {"initial": 82.40, "reported": 90},
            2: {"initial": 77.20, "reported": 80},
        }

        issues = collect_issues(students, calculated, template_name="ECR")

        self.assertEqual([issue["location"]["learnerName"] for issue in issues], ["Ada Cruz", "Ben Santos"])
        self.assertEqual(issues[0]["details"], {
            "savedInitial": 82.42,
            "templateInitial": 82.4,
            "savedReported": 90,
            "templateReported": 90,
            "allowedInitialVariance": 0.01,
        })
        self.assertEqual(issues[1]["details"]["savedReported"], 81)
        self.assertEqual(issues[1]["details"]["templateReported"], 80)
        self.assertTrue(all(issue["code"] == "ECR_GRADE_CALCULATION_MISMATCH" for issue in issues))
        self.assertTrue(all(issue["blocks"] == ["export"] for issue in issues))


    def test_shs_preflight_collects_school_and_track_blockers_before_template_or_file_access(self) -> None:
        validate_export = getattr(shs_class_record_export, "validate_shs_ecr_export", None)
        self.assertTrue(callable(validate_export), "SHS export preflight must exist")

        full = {
            "gradebook": {
                "grade_name": "Grade 11",
                "section_name": "Lakandula",
                "section_track": "Unsupported Track",
                "school_year_name": "2026-2027",
                "status": "Finalized",
                "teacher_name": "Joselito Santos",
                "term_order": 1,
            },
            "students": [{"person_id": 1, "full_name": "Ada Cruz"}],
            "statistics": {"incomplete": 0},
        }

        with patch.object(shs_class_record_export, "_ecr_reference_data", side_effect=AssertionError("template should not be opened")):
            issues = validate_export(
                db=None,
                book=SimpleNamespace(teacher_user_id=1),
                full=full,
                region="",
                division="",
                school_id="30A874",
            )

        self.assertEqual({issue["code"] for issue in issues}, {
            "SCHOOL_REGION_REQUIRED",
            "SCHOOL_DIVISION_REQUIRED",
            "SCHOOL_ID_INVALID",
            "SHS_TRACK_UNSUPPORTED",
        })
        self.assertTrue(all(issue["blocks"] == ["export"] for issue in issues))


if __name__ == "__main__":
    unittest.main()
