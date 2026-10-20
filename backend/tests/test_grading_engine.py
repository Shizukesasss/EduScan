"""Unit tests for the EduScan grading calculation engine.

These tests exercise the pure-function engine in isolation (no database).
"""
from __future__ import annotations

import sys
import os
import unittest

# Add the backend directory to the path so we can import the engine
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.grading_engine import (
    apply_transmutation,
    build_default_transmutation_table,
    calculate_component_percentage,
    calculate_student_grade,
    calculate_weighted_grade,
    determine_grade_status,
    generate_calculation_breakdown,
    round_value,
    validate_gradebook,
)


class TestRoundValue(unittest.TestCase):

    def test_half_up_rounds_correctly(self):
        self.assertEqual(round_value(85.555, 2, "half_up"), 85.56)
        self.assertEqual(round_value(85.554, 2, "half_up"), 85.55)
        self.assertEqual(round_value(85.545, 2, "half_up"), 85.55)
        self.assertEqual(round_value(85.5, 0, "half_up"), 86.0)
        self.assertEqual(round_value(85.4, 0, "half_up"), 85.0)

    def test_floor_always_rounds_down(self):
        self.assertEqual(round_value(85.999, 0, "floor"), 85.0)
        self.assertEqual(round_value(85.999, 2, "floor"), 85.99)

    def test_ceiling_always_rounds_up(self):
        self.assertEqual(round_value(85.001, 0, "ceiling"), 86.0)
        self.assertEqual(round_value(85.001, 2, "ceiling"), 85.01)

    def test_zero_decimal_places(self):
        self.assertEqual(round_value(88.6, 0, "half_up"), 89.0)

    def test_exact_value_no_rounding(self):
        self.assertEqual(round_value(75.0, 2, "half_up"), 75.0)


class TestComponentPercentage(unittest.TestCase):

    def test_partial_exams_normalize_only_scored_portions(self):
        items = [dict(id=index, label=label, max_score=50)
                 for index, label in enumerate(('ST1', 'ST2', 'TE'))]
        for item in items:
            result = calculate_component_percentage(
                [dict(item_id=item['id'], score=44, status='Scored')], items, 'Term Examinations')
            self.assertEqual(result['total_possible'], 50)
            self.assertAlmostEqual(result['percentage'], 88)
            self.assertEqual(round_value(result['percentage'] * 0.3), 26.4)
            self.assertFalse(result['complete'])
        scores = [dict(item_id=0, score=50, status='Scored'), dict(item_id=2, score=0, status='Scored')]
        result = calculate_component_percentage(scores, items, 'Term Examinations')
        self.assertAlmostEqual(result['percentage'], 3000 / 70)
        self.assertFalse(result['complete'])
        scores.insert(1, dict(item_id=1, score=25, status='Scored'))
        self.assertEqual(calculate_component_percentage(scores, items, 'Term Examinations')['percentage'], 45)

    def test_same_max_scores(self):
        items = [{"id": 1, "max_score": 20}, {"id": 2, "max_score": 20}]
        scores = [
            {"item_id": 1, "score": 18, "status": "Scored"},
            {"item_id": 2, "score": 16, "status": "Scored"},
        ]
        result = calculate_component_percentage(scores, items)
        self.assertTrue(result["complete"])
        self.assertEqual(result["total_earned"], 34.0)
        self.assertEqual(result["total_possible"], 40.0)
        self.assertAlmostEqual(result["percentage"], 85.0)

    def test_different_max_scores(self):
        """Total-over-total method: 18/20 + 27/30 + 20/25 = 65/75 = 86.67%"""
        items = [{"id": 1, "max_score": 20}, {"id": 2, "max_score": 30}, {"id": 3, "max_score": 25}]
        scores = [
            {"item_id": 1, "score": 18, "status": "Scored"},
            {"item_id": 2, "score": 27, "status": "Scored"},
            {"item_id": 3, "score": 20, "status": "Scored"},
        ]
        result = calculate_component_percentage(scores, items)
        self.assertTrue(result["complete"])
        self.assertAlmostEqual(result["percentage"], 65.0 / 75.0 * 100, places=2)

    def test_missing_score_makes_incomplete(self):
        items = [{"id": 1, "max_score": 20}, {"id": 2, "max_score": 30}]
        scores = [{"item_id": 1, "score": 18, "status": "Scored"}]
        result = calculate_component_percentage(scores, items)
        self.assertFalse(result["complete"])
        self.assertEqual(result["scored_count"], 1)

    def test_non_scored_status_excluded(self):
        items = [{"id": 1, "max_score": 20}, {"id": 2, "max_score": 30}]
        scores = [
            {"item_id": 1, "score": 18, "status": "Scored"},
            {"item_id": 2, "score": 0, "status": "Excused"},
        ]
        result = calculate_component_percentage(scores, items)
        self.assertFalse(result["complete"])
        self.assertEqual(result["scored_count"], 1)

    def test_all_zeros(self):
        items = [{"id": 1, "max_score": 20}, {"id": 2, "max_score": 30}]
        scores = [
            {"item_id": 1, "score": 0, "status": "Scored"},
            {"item_id": 2, "score": 0, "status": "Scored"},
        ]
        result = calculate_component_percentage(scores, items)
        self.assertTrue(result["complete"])
        self.assertEqual(result["percentage"], 0.0)

    def test_perfect_score(self):
        items = [{"id": 1, "max_score": 50}]
        scores = [{"item_id": 1, "score": 50, "status": "Scored"}]
        result = calculate_component_percentage(scores, items)
        self.assertTrue(result["complete"])
        self.assertAlmostEqual(result["percentage"], 100.0)

    def test_empty_items_returns_incomplete(self):
        result = calculate_component_percentage([], [])
        self.assertFalse(result["complete"])
        self.assertIsNone(result["percentage"])

    def test_absent_status_not_counted(self):
        items = [{"id": 1, "max_score": 20}]
        scores = [{"item_id": 1, "score": None, "status": "Absent"}]
        result = calculate_component_percentage(scores, items)
        self.assertFalse(result["complete"])
        self.assertEqual(result["scored_count"], 0)


class TestWeightedGrade(unittest.TestCase):

    def test_standard_three_components(self):
        results = [
            {"name": "Written Works", "weight": 30, "percentage": 85.0, "complete": True},
            {"name": "Performance Tasks", "weight": 50, "percentage": 90.0, "complete": True},
            {"name": "Quarterly Assessment", "weight": 20, "percentage": 88.0, "complete": True},
        ]
        calc = calculate_weighted_grade(results)
        self.assertTrue(calc["complete"])
        # 85*0.3 + 90*0.5 + 88*0.2 = 25.5 + 45.0 + 17.6 = 88.1
        self.assertAlmostEqual(calc["initial_grade"], 88.1, places=1)

    def test_incomplete_component_nulls_grade(self):
        results = [
            {"name": "WW", "weight": 30, "percentage": 85.0, "complete": True},
            {"name": "PT", "weight": 50, "percentage": None, "complete": False},
            {"name": "QA", "weight": 20, "percentage": 88.0, "complete": True},
        ]
        calc = calculate_weighted_grade(results)
        self.assertFalse(calc["complete"])
        self.assertIsNone(calc["initial_grade"])

    def test_single_component_100_percent(self):
        results = [{"name": "Overall", "weight": 100, "percentage": 92.0, "complete": True}]
        calc = calculate_weighted_grade(results)
        self.assertTrue(calc["complete"])
        self.assertAlmostEqual(calc["initial_grade"], 92.0, places=1)


class TestTransmutation(unittest.TestCase):

    def test_perfect_100(self):
        self.assertEqual(apply_transmutation(100.0), 100)

    def test_near_perfect(self):
        self.assertEqual(apply_transmutation(98.5), 99)

    def test_passing_boundary(self):
        # 60.0 should transmute to 75
        self.assertEqual(apply_transmutation(60.0), 75)

    def test_just_below_60(self):
        # 59.99 should transmute to 74
        self.assertEqual(apply_transmutation(59.99), 74)

    def test_zero(self):
        self.assertEqual(apply_transmutation(0.0), 60)

    def test_middle_range(self):
        # 80.0 → floor((80-60)/1.6) + 75 = floor(12.5) + 75 = 87
        self.assertEqual(apply_transmutation(80.0), 87)

    def test_custom_table(self):
        table = [
            {"min": 0, "max": 49.99, "value": 70},
            {"min": 50, "max": 100, "value": 85},
        ]
        self.assertEqual(apply_transmutation(30.0, table), 70)
        self.assertEqual(apply_transmutation(75.0, table), 85)

    def test_none_input(self):
        self.assertIsNone(apply_transmutation(None))

    def test_clamped_above_100(self):
        self.assertEqual(apply_transmutation(105.0), 100)

    def test_clamped_below_0(self):
        self.assertEqual(apply_transmutation(-5.0), 60)

    def test_default_table_covers_full_range(self):
        table = build_default_transmutation_table()
        # Verify all integers from 60 to 100 appear in values
        values = {entry["value"] for entry in table}
        for v in range(60, 101):
            self.assertIn(v, values, f"Value {v} missing from transmutation table")


class TestGradeStatus(unittest.TestCase):

    def test_passing(self):
        self.assertEqual(determine_grade_status(80, 75), "Passing")

    def test_exact_passing(self):
        self.assertEqual(determine_grade_status(75, 75), "Passing")

    def test_below_passing(self):
        self.assertEqual(determine_grade_status(74, 75), "Below Passing")

    def test_incomplete(self):
        self.assertEqual(determine_grade_status(None, 75), "Incomplete")

    def test_incomplete_even_with_grade(self):
        self.assertEqual(determine_grade_status(80, 75, all_complete=False), "Incomplete")


class TestFullStudentCalculation(unittest.TestCase):

    def setUp(self):
        self.components = [
            {"id": 1, "name": "Written Works", "weight": 30, "component_type": "Written Work"},
            {"id": 2, "name": "Performance Tasks", "weight": 50, "component_type": "Performance Task"},
            {"id": 3, "name": "Quarterly Assessment", "weight": 20, "component_type": "Quarterly Assessment"},
        ]
        self.items_by_component = {
            1: [{"id": 10, "max_score": 20}, {"id": 11, "max_score": 30}],
            2: [{"id": 20, "max_score": 50}, {"id": 21, "max_score": 50}],
            3: [{"id": 30, "max_score": 100}],
        }

    def test_complete_student(self):
        scores = [
            {"item_id": 10, "score": 18, "status": "Scored"},
            {"item_id": 11, "score": 27, "status": "Scored"},
            {"item_id": 20, "score": 45, "status": "Scored"},
            {"item_id": 21, "score": 40, "status": "Scored"},
            {"item_id": 30, "score": 88, "status": "Scored"},
        ]
        result = calculate_student_grade(
            student_scores=scores,
            components=self.components,
            items_by_component=self.items_by_component,
        )
        self.assertTrue(result["complete"])
        self.assertIsNotNone(result["initial_grade"])
        self.assertIsNotNone(result["reported_grade"])
        self.assertIn(result["status"], {"Passing", "Below Passing"})

    def test_incomplete_student(self):
        scores = [
            {"item_id": 10, "score": 18, "status": "Scored"},
            # Missing other scores
        ]
        result = calculate_student_grade(
            student_scores=scores,
            components=self.components,
            items_by_component=self.items_by_component,
        )
        self.assertFalse(result["complete"])
        self.assertIsNone(result["initial_grade"])
        self.assertEqual(result["status"], "Incomplete")

    def test_all_perfect_scores(self):
        scores = [
            {"item_id": 10, "score": 20, "status": "Scored"},
            {"item_id": 11, "score": 30, "status": "Scored"},
            {"item_id": 20, "score": 50, "status": "Scored"},
            {"item_id": 21, "score": 50, "status": "Scored"},
            {"item_id": 30, "score": 100, "status": "Scored"},
        ]
        result = calculate_student_grade(
            student_scores=scores,
            components=self.components,
            items_by_component=self.items_by_component,
        )
        self.assertTrue(result["complete"])
        self.assertAlmostEqual(result["initial_grade"], 100.0, places=1)
        self.assertEqual(result["reported_grade"], 100)
        self.assertEqual(result["status"], "Passing")

    def test_custom_transmutation(self):
        scores = [
            {"item_id": 10, "score": 15, "status": "Scored"},
            {"item_id": 11, "score": 22, "status": "Scored"},
            {"item_id": 20, "score": 35, "status": "Scored"},
            {"item_id": 21, "score": 38, "status": "Scored"},
            {"item_id": 30, "score": 70, "status": "Scored"},
        ]
        custom_table = [{"min": 0, "max": 100, "value": 99}]  # everything becomes 99
        result = calculate_student_grade(
            student_scores=scores,
            components=self.components,
            items_by_component=self.items_by_component,
            transmutation_table=custom_table,
        )
        self.assertEqual(result["reported_grade"], 99)


class TestValidation(unittest.TestCase):

    def test_no_components_error(self):
        issues = validate_gradebook([], {}, {}, [1, 2])
        self.assertTrue(any(i["code"] == "NO_COMPONENTS" for i in issues))

    def test_weight_total_invalid(self):
        components = [{"id": 1, "name": "WW", "weight": 50, "sequence": 0}]
        issues = validate_gradebook(components, {1: [{"id": 10, "max_score": 20}]}, {}, [])
        self.assertTrue(any(i["code"] == "WEIGHT_TOTAL_INVALID" for i in issues))

    def test_valid_gradebook_no_errors(self):
        components = [
            {"id": 1, "name": "WW", "weight": 30, "sequence": 0},
            {"id": 2, "name": "PT", "weight": 50, "sequence": 1},
            {"id": 3, "name": "QA", "weight": 20, "sequence": 2},
        ]
        items = {
            1: [{"id": 10, "max_score": 20}],
            2: [{"id": 20, "max_score": 50}],
            3: [{"id": 30, "max_score": 100}],
        }
        student_scores = {
            1: [
                {"item_id": 10, "score": 18, "status": "Scored"},
                {"item_id": 20, "score": 45, "status": "Scored"},
                {"item_id": 30, "score": 88, "status": "Scored"},
            ],
        }
        issues = validate_gradebook(components, items, student_scores, [1])
        errors = [i for i in issues if i["level"] == "error"]
        self.assertEqual(len(errors), 0)

    def test_missing_student_scores_warning(self):
        components = [{"id": 1, "name": "WW", "weight": 100, "sequence": 0}]
        items = {1: [{"id": 10, "max_score": 20}]}
        issues = validate_gradebook(components, items, {}, [1, 2])
        warnings = [i for i in issues if i["code"] == "STUDENT_MISSING_SCORES"]
        self.assertEqual(len(warnings), 2)

    def test_component_no_items_error(self):
        components = [{"id": 1, "name": "WW", "weight": 100, "sequence": 0}]
        issues = validate_gradebook(components, {}, {}, [])
        self.assertTrue(any(i["code"] == "COMPONENT_NO_ITEMS" for i in issues))

    def test_item_invalid_max_score(self):
        components = [{"id": 1, "name": "WW", "weight": 100, "sequence": 0}]
        items = {1: [{"id": 10, "max_score": 0}]}
        issues = validate_gradebook(components, items, {}, [])
        self.assertTrue(any(i["code"] == "ITEM_INVALID_MAX" for i in issues))

    def test_duplicate_component_name_warning(self):
        components = [
            {"id": 1, "name": "Written Works", "weight": 50, "sequence": 0},
            {"id": 2, "name": "Written Works", "weight": 50, "sequence": 1},
        ]
        items = {1: [{"id": 10, "max_score": 20}], 2: [{"id": 20, "max_score": 20}]}
        issues = validate_gradebook(components, items, {}, [])
        self.assertTrue(any(i["code"] == "COMPONENT_DUPLICATE_NAME" for i in issues))


class TestCalculationBreakdown(unittest.TestCase):

    def test_generates_readable_breakdown(self):
        calc_result = {
            "initial_grade": 88.1,
            "reported_grade": 91,
            "status": "Passing",
            "complete": True,
            "component_grades": [
                {"name": "Written Works", "percentage": 85.0, "weight": 30, "weighted_score": 25.5},
                {"name": "Performance Tasks", "percentage": 90.0, "weight": 50, "weighted_score": 45.0},
                {"name": "Quarterly Assessment", "percentage": 88.0, "weight": 20, "weighted_score": 17.6},
            ],
        }
        breakdown = generate_calculation_breakdown("Juan Dela Cruz", calc_result, "DepEd K-12", 75)
        self.assertEqual(breakdown["student_name"], "Juan Dela Cruz")
        self.assertEqual(len(breakdown["components"]), 3)
        self.assertIn("85.00 × 30% = 25.50", breakdown["components"][0]["formula"])
        self.assertEqual(breakdown["reported_grade"], 91)
        self.assertEqual(breakdown["status"], "Passing")


if __name__ == "__main__":
    unittest.main()
