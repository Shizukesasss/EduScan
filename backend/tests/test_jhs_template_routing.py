import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from app.services import reports
from app.services.class_record_export import _direct_template_grade_formula, subject_template


class JHSTemplateRoutingTests(unittest.TestCase):
    def test_direct_export_formula_rounds_initial_grade_without_helper_table(self):
        self.assertEqual(
            _direct_template_grade_formula('AB', 18),
            'IF(AB18="","",ROUND(MAX(0,MIN(100,AB18)),0))',
        )

    def test_new_jhs_elective_uses_core_template(self):
        self.assertEqual(subject_template('Research Elective', is_elective=True),
                         ('core', 'ENGLISH - Grade 7-10 Class Record.xlsx'))
        full = {'policy': {'rounding_method': 'half_up', 'rounding_decimal_places': 2}, 'components': [{'component_type': 'Term Examinations'}], 'gradebook': {'grade_name': '7', 'subject_name': 'Research Elective'}}
        db = Mock()
        db.get.return_value.subject.is_elective = True
        for all_terms in (False, True):
            with patch('app.services.grading.get_gradebook_full', return_value=full), \
                 patch('app.services.class_record_export.export_jhs', return_value='elective.xlsx') as export:
                self.assertEqual(reports.generate_gradebook_report_xlsx(db, 1, all_terms=all_terms), 'elective.xlsx')
                self.assertEqual(export.call_args.args[4].name, 'ENGLISH - Grade 7-10 Class Record.xlsx')

    def test_jhs_subjects_use_supplied_workbooks_for_both_exports(self):
        for subject in ('MATHEMATICS', 'SCIENCE', 'ENGLISH', 'FILIPINO',
                        'ARALING PANLIPUNAN', 'VALUES EDUCATION', 'TLE', 'MAPEH'):
            for all_terms in (False, True):
                with self.subTest(subject=subject, all_terms=all_terms):
                    full = {'policy': {'rounding_method': 'half_up', 'rounding_decimal_places': 2}, 'components': [{'component_type': 'Term Examinations'}], 'gradebook': {'grade_name': '7', 'subject_name': subject}}
                    with patch('app.services.grading.get_gradebook_full', return_value=full), \
                         patch('app.services.class_record_export.export_jhs', return_value='template.xlsx') as export:
                        result = reports.generate_gradebook_report_xlsx(Mock(), 1, all_terms=all_terms)
                    self.assertEqual(result, 'template.xlsx')
                    self.assertTrue(export.call_args.args[4].is_file())
                    self.assertEqual(export.call_args.kwargs['all_terms'], all_terms)

    def test_template_mismatch_is_reported_without_generic_fallback(self):
        full = {'policy': {'rounding_method': 'half_up', 'rounding_decimal_places': 2}, 'components': [{'component_type': 'Term Examinations'}], 'gradebook': {'grade_name': '7', 'subject_name': 'ENGLISH'}}
        with patch('app.services.grading.get_gradebook_full', return_value=full), \
             patch('app.services.class_record_export.export_jhs', side_effect=HTTPException(409, 'Policy mismatch')), \
             patch('app.services.adaptive_class_record.export_adaptive') as adaptive:
            with self.assertRaises(HTTPException):
                reports.generate_gradebook_report_xlsx(Mock(), 1)
            adaptive.assert_not_called()

    def test_mapeh_uses_combined_workbook(self):
        kind, filename = subject_template('MAPEH')
        self.assertEqual(kind, 'mapeh')
        self.assertIn('MUSIC AND ARTS AND PE-HEALTH', filename)
