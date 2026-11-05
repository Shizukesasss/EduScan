import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_annex_g as fixtures
from app import main
from app.auth import create_token
from app.models import GeneratedReport

from app.services import reports as reports_service
from app.services.settings_store import set_json
from test_annex_g_pdf import sample_report

class AnnexGPdfApiTests(unittest.TestCase):
    add_enrollment = fixtures.AnnexGImportTests.add_enrollment
    add_gradebook = fixtures.AnnexGImportTests.add_gradebook
    tearDown = fixtures.AnnexGImportTests.tearDown

    def setUp(self):
        fixtures.AnnexGImportTests.setUp(self)
        self.enrollment = self.add_enrollment()
        self.report = sample_report()
        self.report.update(school_year_id=self.year.id, grade='7', section='Jose', term_name='Term 3')
        self.report['learners'][0]['enrollment_id'] = self.enrollment.id

    def test_http_permissions_and_pdf_headers(self):
        def get_db():
            yield self.db
        main.app.dependency_overrides[main.get_db] = get_db
        try:
            client = TestClient(main.app)
            for user in (self.teacher, self.admin, self.records):
                user.must_change_password = False
            self.db.commit()
            teacher_headers = {'Authorization': f'Bearer {create_token(self.teacher)}'}
            admin_headers = {'Authorization': f'Bearer {create_token(self.admin)}'}
            with patch.object(main, 'build_annex_g_section', return_value=self.report):
                response = client.get(f'/api/annex-g/preview/{self.enrollment.id}/pdf?term_order=3',headers=teacher_headers)
                self.assertEqual(response.status_code,200,response.text if response.status_code != 200 else '')
                self.assertEqual(response.headers['content-type'],'application/pdf')
                self.assertTrue(response.content.startswith(b'%PDF-'))
                self.assertEqual(client.get('/api/annex-g/school-profile',headers=teacher_headers).status_code,403)
                self.assertEqual(client.post(f'/api/annex-g/release/{self.enrollment.id}?term_order=3',headers=admin_headers).status_code,403)
                self.assertEqual(client.get(f'/api/annex-g/preview/{self.enrollment.id}/pdf?term_order=4',headers=admin_headers).status_code,422)
        finally:
            main.app.dependency_overrides.clear()

    def test_authorized_draft_is_a_pdf_and_creates_no_release(self):
        with patch.object(main, 'build_annex_g_section', return_value=self.report):
            response = main.annex_g_preview_pdf(self.enrollment.id, 3, self.db, self.teacher)
        self.assertEqual(response.media_type, 'application/pdf')
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertIn('DRAFT', PdfReader(io.BytesIO(response.body)).pages[0].extract_text())
        self.assertEqual(self.db.query(GeneratedReport).count(), 0)

    def test_preview_rejects_placement_outside_selected_term_roster(self):
        self.report['learners'] = []
        with patch.object(main, 'build_annex_g_section', return_value=self.report):
            with self.assertRaises(HTTPException) as error:
                main.annex_g_preview_pdf(self.enrollment.id, 1, self.db, self.teacher)
        self.assertEqual(error.exception.status_code, 404)

    def test_class_record_only_learner_can_preview_but_cannot_release(self):
        self.db.delete(self.enrollment)
        self.db.commit()
        self.add_gradebook(self.math,1,100)
        count=self.db.query(GeneratedReport).count()
        response=main.annex_g_class_record_draft_pdf(self.learner.id,self.year.id,'7','Jose',1,self.db,self.teacher)
        text=PdfReader(io.BytesIO(response.body)).pages[0].extract_text()
        self.assertIn('DRAFT',text)
        self.assertIn('Mathematics',text)
        self.assertIn('100',text)
        self.assertEqual(self.db.query(GeneratedReport).count(),count)
        self.assertEqual(self.db.query(fixtures.LearnerEnrollment).count(),0)
        with self.assertRaises(HTTPException) as error:
            main.release_annex_g(-self.learner.id,1,self.db,self.records)
        self.assertEqual(error.exception.status_code,404)
        self.admin.role='teacher'
        with self.assertRaises(HTTPException) as error:
            main.annex_g_class_record_draft_pdf(self.learner.id,self.year.id,'7','Jose',1,self.db,self.admin)
        self.assertEqual(error.exception.status_code,403)

    def test_profile_is_validated_and_audited(self):
        payload = main.AnnexGSchoolProfilePayload(name='School',region='V',division='Albay',district='District',municipality='City',province='Province')
        result = main.save_annex_g_school_profile(payload, self.db, self.admin)
        self.assertEqual(result['district'], 'District')
        self.assertEqual(main.annex_g_school_profile(self.db, self.admin)['name'], 'School')

    def test_release_pdf_reissue_preserves_previous_bytes_and_hash(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.object(reports_service,'REPORT_DIR',Path(directory)), patch.object(main,'REPORT_DIR',Path(directory)), patch.object(main,'build_annex_g_section',return_value=self.report):
            first = main.release_annex_g(self.enrollment.id,3,self.db,self.records)
            old = self.db.get(GeneratedReport,first['id'])
            original = Path(old.file_path).read_bytes()
            second = main.release_annex_g(self.enrollment.id,3,self.db,self.records)
            self.assertEqual(old.status,'Superseded')
            self.assertEqual(Path(old.file_path).read_bytes(),original)
            self.assertEqual(first['sha256'],hashlib.sha256(original).hexdigest())
            current = self.db.get(GeneratedReport,second['id'])
            self.assertTrue(current.filename.endswith('.pdf'))
            self.assertEqual(json.loads(current.parameters_json)['paper_size'], 'A5 landscape')
            self.assertNotIn('DRAFT', PdfReader(current.file_path).pages[0].extract_text())
            response = main.annex_g_released_file(current.id,self.db,self.teacher)
            self.assertEqual(response.media_type,'application/pdf')
            self.assertEqual(len(list(Path(directory).glob('*.pdf'))),2)

    def test_legacy_html_and_tampered_release(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path=Path(directory)/'old.html'; path.write_text('<p>Archived HTML</p>',encoding='utf-8')
            item=GeneratedReport(id='old',report_type='Annex G',filename='old.html',file_path=str(path),file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),parameters_json=json.dumps({'enrollment_id':self.enrollment.id}),status='Released',generated_by=self.records.id,generated_by_name=self.records.full_name,generated_by_role='records_officer')
            self.db.add(item); self.db.commit()
            response=main.annex_g_released_file('old',self.db,self.teacher)
            self.assertEqual(response.media_type,'text/html')
            self.assertIn(b'Archived HTML',response.body)
            path.write_text('tampered')
            with self.assertRaises(HTTPException) as error:
                main.annex_g_released_file('old',self.db,self.teacher)
            self.assertEqual(error.exception.status_code,409)

    def test_shared_registration_retains_committed_artifact_when_refresh_fails(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.object(reports_service,'REPORT_DIR',Path(directory)):
            source=Path(directory)/'source.pdf'
            source.write_bytes(b'%PDF-synthetic')
            with patch.object(self.db,'refresh',side_effect=RuntimeError('refresh failed')):
                with self.assertRaisesRegex(RuntimeError,'refresh failed'):
                    reports_service.register_report(self.db,source,'Test report',{},self.admin)
            item=self.db.scalars(select(GeneratedReport)).one()
            self.assertTrue(Path(item.file_path).exists())
            self.assertEqual(Path(item.file_path).read_bytes(),source.read_bytes())

    def test_failed_final_commit_preserves_previous_release_and_removes_new_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.object(reports_service,'REPORT_DIR',Path(directory)), patch.object(main,'REPORT_DIR',Path(directory)), patch.object(main,'build_annex_g_section',return_value=self.report):
            first=main.release_annex_g(self.enrollment.id,3,self.db,self.records)
            with patch.object(self.db,'commit',side_effect=RuntimeError('commit failed')):
                with self.assertRaisesRegex(RuntimeError,'commit failed'):
                    main.release_annex_g(self.enrollment.id,3,self.db,self.records)
            self.assertEqual(self.db.get(GeneratedReport,first['id']).status,'Released')
            self.assertEqual(self.db.query(GeneratedReport).count(),1)
            self.assertEqual(len(list(Path(directory).glob('*.pdf'))),1)

    def test_copy_and_flush_failures_preserve_existing_release(self):
        for failure in ('copy', 'flush'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.object(reports_service,'REPORT_DIR',Path(directory)), patch.object(main,'REPORT_DIR',Path(directory)), patch.object(main,'build_annex_g_section',return_value=self.report):
                previous=main.release_annex_g(self.enrollment.id,3,self.db,self.records)
                original_flush = self.db.flush
                def fail_report_flush(*args, **kwargs):
                    if any(isinstance(item, GeneratedReport) for item in self.db.new):
                        raise RuntimeError('flush failed')
                    return original_flush(*args, **kwargs)
                failing = patch.object(reports_service.shutil,'copy2',side_effect=OSError('copy failed')) if failure=='copy' else patch.object(self.db,'flush',side_effect=fail_report_flush)
                with failing:
                    with self.assertRaisesRegex((OSError, RuntimeError), failure+' failed'):
                        main.release_annex_g(self.enrollment.id,3,self.db,self.records)
                self.assertEqual(self.db.get(GeneratedReport,previous['id']).status,'Released')
                self.assertEqual(len(list(Path(directory).glob('*.pdf'))),1)

    def test_layout_failure_and_unrelated_teacher_are_blocked(self):
        with patch.object(main,'build_annex_g_section',return_value=self.report):
            self.report['learners'][0]['comments']['1']='too much text '*1000
            with self.assertRaises(HTTPException) as error:
                main.release_annex_g(self.enrollment.id,3,self.db,self.records)
            self.assertEqual(error.exception.status_code,409)
            with self.assertRaises(HTTPException) as error:
                main.annex_g_preview_pdf(self.enrollment.id,3,self.db,self.records)
            self.assertEqual(error.exception.status_code,409)
        unrelated=self.admin
        unrelated.role='teacher'
        with self.assertRaises(HTTPException) as error:
            main.annex_g_preview_pdf(self.enrollment.id,3,self.db,unrelated)
        self.assertEqual(error.exception.status_code,403)

if __name__=='__main__': unittest.main()
