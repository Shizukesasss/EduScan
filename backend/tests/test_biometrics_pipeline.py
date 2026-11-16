from unittest.mock import MagicMock

import numpy as np
from sqlalchemy.orm import Session

from app.models import Person
from app.services.biometrics import BiometricService, ProcessedFace


def face_with_eye_count(eye_count):
    return ProcessedFace(np.zeros((10, 10), dtype=np.uint8), b"", 100.0, (0, 0, 10, 10), eye_count, "sig")


def test_verify_liveness_accepts_a_complete_blink():
    service = BiometricService()
    db = MagicMock(spec=Session)
    person = Person(id=1)
    config = {"liveness_enabled": True, "liveness_window_seconds": 8}
    state = {}

    outcomes = [
        service.verify_liveness(db, person, face_with_eye_count(count), config=config, test_state=state)
        for count in (2, 0, 2)
    ]

    assert [passed for passed, _ in outcomes] == [False, False, True]
    assert "Natural blink sequence verified" in outcomes[-1][1]
    assert not state


def test_verify_liveness_waits_without_a_blink():
    service = BiometricService()
    db = MagicMock(spec=Session)
    person = Person(id=2)
    config = {"liveness_enabled": True, "liveness_window_seconds": 8}
    state = {}

    outcomes = [
        service.verify_liveness(db, person, face_with_eye_count(2), config=config, test_state=state)
        for _ in range(3)
    ]

    assert all(not passed for passed, _ in outcomes)
    assert "waiting for a blink" in outcomes[-1][1]


def test_verify_liveness_respects_the_administrator_setting():
    service = BiometricService()
    db = MagicMock(spec=Session)
    service.runtime_config = MagicMock(return_value={"liveness_enabled": False})

    passed, message = service.verify_liveness(db, Person(id=3), face_with_eye_count(2))

    assert passed
    assert "disabled by an authorized administrator" in message
