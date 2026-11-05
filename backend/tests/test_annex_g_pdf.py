from __future__ import annotations
import copy
import io
import sys
import unittest
from unittest.mock import Mock
from pathlib import Path
from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reportlab.pdfbase import pdfmetrics
from app.services.annex_g_pdf import AnnexGLayoutError, _Form, _fonts, X_SCALE, Y_SCALE, LAYOUT_HEIGHT, render_annex_g_pdf


def sample_report(term=3):
    names = ['Filipino', 'English', 'Mathematics', 'Science', 'Araling Panlipunan (AP)', 'GMRC / Values Education', 'EPP / TLE', 'MAPEH']
    areas = [{'name': name, 'term_grades': {str(n): 80+n for n in range(1,term+1)}, 'final_grade': 82 if term == 3 else None, 'remarks': 'Passed' if term == 3 else ''} for name in names]
    areas[-1]['subareas'] = [{'name': name, 'term_grades': {str(n): 80+n for n in range(1,term+1)}, 'final_grade': 82 if term == 3 else None} for name in ['Music and Arts', 'Physical Education and Health']]
    return {'school_year': '2026-2027', 'term_order': term, 'school': {'name': 'SAN JOSE NATIONAL HIGH SCHOOL', 'region': 'V', 'division': 'ALBAY', 'district': 'Malilipot', 'municipality': 'Malilipot', 'province': 'Albay', 'school_head': 'Verified School Head'}, 'adviser_name': 'Verified Adviser', 'learners': [{'enrollment_id': 1, 'full_name': 'Peña, José María', 'lrn': '001234567890', 'age': 14, 'sex': 'Male', 'grade': '7', 'section': 'Jose', 'learning_areas': areas, 'general_average': 82 if term == 3 else None, 'attendance': [{'month': f'2026-{n:02d}', 'days_of_class': 20, 'days_present': 18, 'days_absent': 2} for n in range(1,13)], 'comments': {str(n): 'Shows consistent effort and progress.' for n in range(1,term+1)}, 'blockers': []}], 'blockers': []}


class AnnexGPdfTests(unittest.TestCase):
    def test_real_single_page_a5_landscape_pdf_contains_form_and_exact_values(self):
        data = render_annex_g_pdf(sample_report(), 1, draft=False)
        self.assertTrue(data.startswith(b'%PDF-'))
        pdf = PdfReader(io.BytesIO(data))
        self.assertEqual(len(pdf.pages), 1)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), 595.28, places=1)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), 419.53, places=1)
        self.assertIn('A5 landscape', pdf.metadata.subject)
        text = pdf.pages[0].extract_text()
        for expected in ['Peña, José María', '001234567890', 'Mathematics', 'Music and Arts', 'Physical Education and Health', 'General Average', 'ATTENDANCE RECORD', 'TEACHER', 'CERTIFICATE OF TRANSFER', 'CANCELLATION OF ELIGIBILITY TO TRANSFER', 'Verified Adviser', 'Verified School Head']:
            self.assertIn(expected, text)
        self.assertNotIn('DRAFT', text)
        self.assertNotIn('date_of_birth', text)

    def test_field_underline_starts_immediately_after_measured_label(self):
        _fonts()
        canvas = Mock()
        form = _Form(canvas)
        label = 'Track (SHS only):'
        form.field(label, '', 32, 257, 255)
        line_start = canvas.line.call_args.args[0]
        expected = 32 + pdfmetrics.stringWidth(label, 'AnnexSerif', 7) + 4
        self.assertAlmostEqual(line_start, expected*X_SCALE, places=2)

    def test_wrapped_name_gets_clear_gap_before_rule_and_following_fields(self):
        _fonts()
        canvas = Mock()
        form = _Form(canvas)
        name = 'TEST-MANUEL-FEMALE-ALPHA, Learner'
        y = 201
        row_height = form.field('Name:', name, 32, y, 160)
        line_y = LAYOUT_HEIGHT - canvas.line.call_args.args[1]/Y_SCALE
        label_width = pdfmetrics.stringWidth('Name:', 'AnnexSerif', 7) + 4
        style = ParagraphStyle('name-test', fontName='AnnexSerif', fontSize=7.6, leading=7.6*1.12)
        paragraph = Paragraph(name, style)
        _, name_height = paragraph.wrap((160-label_width-2)*X_SCALE, 23*Y_SCALE)
        self.assertGreaterEqual(line_y - (y + name_height/Y_SCALE), 3)
        self.assertGreaterEqual(row_height + .01, line_y-y+4)

    def test_identity_rules_stay_close_to_single_line_and_blank_fields(self):
        _fonts()
        for label, value, width in [('Name:', 'Learner', 160), ('Age:', 12, 40), ('Track (SHS only):', '', 255)]:
            with self.subTest(label=label):
                canvas = Mock()
                _Form(canvas).field(label, value, 32, 201, width)
                rule_offset = LAYOUT_HEIGHT - canvas.line.call_args.args[1]/Y_SCALE - 201
                self.assertLessEqual(rule_offset, 16)

    def test_draft_and_earlier_terms_do_not_invent_future_grades(self):
        report = sample_report(1)
        before = copy.deepcopy(report)
        text = PdfReader(io.BytesIO(render_annex_g_pdf(report, 1, draft=True))).pages[0].extract_text()
        self.assertIn('DRAFT', text)
        self.assertNotIn('82', text)
        self.assertNotIn('83', text)
        self.assertEqual(report, before)

    def test_long_names_wrap_and_literal_markup_remains_text(self):
        report = sample_report()
        report['learners'][0]['full_name'] = 'Peña <Learner> & José María de la Cruz'
        text = PdfReader(io.BytesIO(render_annex_g_pdf(report, 1, draft=True))).pages[0].extract_text()
        self.assertIn('<Learner>', text)
        self.assertIn('José', text)

    def test_unbounded_comments_and_subjects_fail_without_truncation(self):
        report = sample_report()
        report['learners'][0]['comments']['1'] = 'Very long comment ' * 1000
        with self.assertRaisesRegex(AnnexGLayoutError, 'comment'):
            render_annex_g_pdf(report, 1, draft=False)
        report = sample_report()
        report['learners'][0]['learning_areas'] *= 10
        with self.assertRaisesRegex(AnnexGLayoutError, 'learning'):
            render_annex_g_pdf(report, 1, draft=False)

    def test_school_id_is_printed_with_the_school_header(self):
        report = sample_report()
        report['school']['school_id'] = '301875'
        text = PdfReader(io.BytesIO(render_annex_g_pdf(report, 1, draft=True))).pages[0].extract_text()
        self.assertIn('School ID: 301875', text)

    def test_school_year_touching_thirteen_months_preserves_both_years(self):
        report = sample_report()
        report['attendance_months'] = [f'2026-{n:02d}' for n in range(5,13)] + [f'2027-{n:02d}' for n in range(1,6)]
        pdf = PdfReader(io.BytesIO(render_annex_g_pdf(report,1,draft=True)))
        self.assertEqual(len(pdf.pages),1)
        text = pdf.pages[0].extract_text()
        self.assertRegex(text,r'May\s+26')
        self.assertRegex(text,r'May\s+27')

    def test_wrong_learner_does_not_export_another_person(self):
        with self.assertRaisesRegex(ValueError, 'learner'):
            render_annex_g_pdf(sample_report(), 999, draft=True)

if __name__ == '__main__':
    unittest.main()
