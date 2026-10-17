"""Model recovery diagnostics with synthetic images and an isolated database."""
from pathlib import Path
import hashlib
import unittest
from cryptography.fernet import Fernet
import numpy as np
from sqlalchemy import select

from tests import test_duplicate_enrollment as helpers
from app.models import BiometricModel
from app.main import biometric_enrollments


class ModelReadinessTest(unittest.TestCase):
    def setUp(self):
        self.fixture = helpers.DuplicateEnrollmentTest()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.service = self.fixture.service

    def tearDown(self):
        self.fixture.tearDown()

    def trained_model(self):
        self.fixture.enroll(self.fixture.first, helpers.face_set())
        return self.db.scalar(select(BiometricModel).where(BiometricModel.active.is_(True)))

    def clear_cache(self):
        self.service._recognizer = None
        self.service._model_path = None

    def test_no_model_reports_not_trained(self):
        result = self.service.model_readiness(self.db)
        self.assertFalse(result['available'])
        self.assertEqual(result['code'], 'model_not_trained')

    def test_active_record_without_file_is_unavailable(self):
        model = self.trained_model()
        Path(model.file_path).unlink()
        # A cached recognizer must not conceal a missing encrypted model file.
        result = self.service.model_readiness(self.db)
        self.assertFalse(result['available'])
        self.assertEqual(result['code'], 'model_file_missing')
        self.assertTrue(model.active)

    def test_copied_model_resolves_without_rewriting_shared_metadata(self):
        model = self.trained_model()
        filename = Path(model.file_path).name
        model.file_path = 'C:\\UnavailableComputer\\models\\' + filename
        self.db.commit()
        self.clear_cache()
        result = self.service.model_readiness(self.db)
        self.assertTrue(result['available'])
        self.assertEqual(model.file_path, 'C:\\UnavailableComputer\\models\\' + filename)

    def test_model_with_wrong_key_is_blocked(self):
        self.trained_model()
        self.clear_cache()
        self.service.fernet = Fernet(Fernet.generate_key())
        result = self.service.model_readiness(self.db)
        self.assertFalse(result['available'])
        self.assertEqual(result['code'], 'model_key_mismatch')
        self.assertEqual(list(helpers.biometrics.MODEL_DIR.glob('load-*.yml')), [])

    def test_model_hash_mismatch_is_blocked(self):
        model = self.trained_model()
        model.sha256 = '0' * 64
        self.db.commit()
        self.clear_cache()
        result = self.service.model_readiness(self.db)
        self.assertFalse(result['available'])
        self.assertEqual(result['code'], 'model_integrity_failed')

    def test_copied_sample_resolves_and_verifies_plaintext_hash(self):
        self.trained_model()
        sample = self.fixture.samples(self.fixture.first)[0]
        expected = self.service._load_sample_image(sample)
        filename = Path(sample.encrypted_path).name
        sample.encrypted_path = 'C:\\UnavailableComputer\\samples\\' + filename
        self.db.commit()
        np.testing.assert_array_equal(self.service._load_sample_image(sample), expected)
        self.assertEqual(sample.encrypted_path, 'C:\\UnavailableComputer\\samples\\' + filename)
        sample.sha256 = hashlib.sha256(b'incorrect data').hexdigest()
        with self.assertRaisesRegex(RuntimeError, 'integrity check'):
            self.service._load_sample_image(sample)

    def test_registered_person_without_samples_is_in_registry(self):
        self.fixture.enroll(self.fixture.first, helpers.face_set())
        self.fixture.second.active = False
        self.db.commit()
        rows = biometric_enrollments(db=self.db, _=self.fixture.admin)
        self.assertEqual([row['person_id'] for row in rows], [self.fixture.first.id])
        self.fixture.second.active = True
        self.db.commit()
        rows = biometric_enrollments(db=self.db, _=self.fixture.admin)
        second = next(row for row in rows if row['person_id'] == self.fixture.second.id)
        self.assertEqual(second['sample_count'], 0)
        self.assertTrue(second['active'])
        self.assertTrue(second['biometric_consent'])


if __name__ == '__main__':
    unittest.main()
