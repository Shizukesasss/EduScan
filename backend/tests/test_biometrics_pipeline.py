import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from app.services.biometrics import BiometricService, ProcessedFace
from app.models import Person

@pytest.fixture
def mock_db():
    db = MagicMock(spec=Session)
    return db

@pytest.fixture
def biometric_service():
    service = BiometricService()
    # Mock config to use passive liveness
    service.runtime_config = MagicMock(return_value={
        "threshold": 80.0,
        "liveness_enabled": True,
        "liveness_mode": "passive",
        "liveness_window_seconds": 8,
        "review_failure_threshold": 4,
        "confirmation_frames_needed": 3,
        "confirmation_window_seconds": 7.0,
        "margin_threshold": 8.0,
    })
    return service

def test_verify_liveness_passive_success(biometric_service, mock_db):
    person = MagicMock(spec=Person)
    person.id = 1
    
    # 3 frames with varying eye counts -> should pass
    buffer = [
        {"ts": datetime.utcnow(), "distance": 45.0, "margin": 10.0, "eye_count": 2},
        {"ts": datetime.utcnow(), "distance": 46.0, "margin": 9.0,  "eye_count": 0},
        {"ts": datetime.utcnow(), "distance": 44.0, "margin": 11.0, "eye_count": 2},
    ]
    face = ProcessedFace(np.zeros((10,10), dtype=np.uint8), b"", 100.0, (0,0,10,10), 2, "sig")
    
    passed, msg = biometric_service.verify_liveness(mock_db, person, face, buffer, "passive")
    assert passed is True
    assert "Natural eye movement detected" in msg

def test_verify_liveness_passive_fail_no_variation(biometric_service, mock_db):
    person = MagicMock(spec=Person)
    person.id = 2
    
    # All frames have the exact same eye_count -> should fail
    buffer = [
        {"ts": datetime.utcnow(), "distance": 45.0, "margin": 10.0, "eye_count": 2},
        {"ts": datetime.utcnow(), "distance": 46.0, "margin": 9.0,  "eye_count": 2},
        {"ts": datetime.utcnow(), "distance": 44.0, "margin": 11.0, "eye_count": 2},
    ]
    face = ProcessedFace(np.zeros((10,10), dtype=np.uint8), b"", 100.0, (0,0,10,10), 2, "sig")
    
    passed, msg = biometric_service.verify_liveness(mock_db, person, face, buffer, "passive")
    assert passed is False
    assert "keep your face in frame; slight natural movement" in msg

def test_verify_liveness_off(biometric_service, mock_db):
    person = MagicMock(spec=Person)
    person.id = 3
    
    buffer = [{"ts": datetime.utcnow(), "distance": 45.0, "margin": 10.0, "eye_count": 2}]
    face = ProcessedFace(np.zeros((10,10), dtype=np.uint8), b"", 100.0, (0,0,10,10), 2, "sig")
    
    passed, msg = biometric_service.verify_liveness(mock_db, person, face, buffer, "off")
    assert passed is True
    assert "disabled by an authorized administrator" in msg
