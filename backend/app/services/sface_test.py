"""Experimental identity matcher for the read-only Camera Test endpoint only."""

import cv2
import numpy as np
from fastapi import HTTPException
from cryptography.fernet import InvalidToken
from sqlalchemy import select

from ..models import BiometricSample, Person
from ..config import settings


from .face_identity import embedding, MIN_SIMILARITY


def recognize_test_frames(db, frames, biometrics):
    if not settings.biometric_enabled:
        raise HTTPException(503, 'Biometric processing is disabled by server configuration.')
    samples = db.scalars(select(BiometricSample).join(Person).where(
        Person.active.is_(True), Person.biometric_consent.is_(True)
    ).order_by(BiometricSample.person_id, BiometricSample.id)).all()
    if not samples:
        raise HTTPException(422, 'No authorized face enrollments are available for SFace testing.')
    gallery = []
    people = {}
    for sample in samples:
        try:
            feature = embedding(biometrics._load_sample_image(sample), biometrics)
        except (OSError, RuntimeError, ValueError, InvalidToken, cv2.error, HTTPException) as error:
            raise HTTPException(503, 'An existing enrollment could not be read or aligned for SFace testing. The enrollment is unchanged.') from error
        gallery.append((sample.person_id, feature))
        if sample.person_id not in people:
            people[sample.person_id] = db.get(Person, sample.person_id)
    config = biometrics.runtime_config(db)
    blink_state = {}
    verified = set()
    observed = {}
    results = []
    comparisons = []
    checked = maximum = max_matched = 0
    last_error = None
    for frame in frames:
        try:
            faces = biometrics.process_faces(frame, strict=True, with_identity=True)
        except HTTPException as error:
            if error.status_code != 422:
                raise
            last_error = error
            results, comparisons = [], []
            continue
        checked += 1
        maximum = max(maximum, len(faces))
        results, comparisons, candidates = [], [], []
        for index, face in enumerate(faces):
            scores = {}
            message = 'No enrolled identity met the SFace similarity cutoff.'
            try:
                feature = face.identity_feature if face.identity_feature is not None else embedding(face.image, biometrics)
                for person_id, stored in gallery:
                    score = float(np.clip(feature @ stored, -1, 1))
                    scores[person_id] = max(score, scores.get(person_id, -1))
            except HTTPException as error:
                if error.status_code != 422:
                    raise
                message = str(error.detail)
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            qualifying = [person_id for person_id, score in ranked if score >= MIN_SIMILARITY]
            person_id = qualifying[0] if len(qualifying) == 1 else None
            if len(qualifying) > 1:
                message = 'This face resembles more than one enrollment. Identity is uncertain; no attendance is recorded.'
            comparisons.append({'face': index + 1, 'threshold': MIN_SIMILARITY,
                                'candidates': [{'name': people[key].full_name, 'similarity': round(score, 4)}
                                               for key, score in ranked[:2]]})
            candidates.append((face, person_id, ranked[0][1] if ranked else None, message))
        labels = [person_id for _, person_id, _, _ in candidates if person_id is not None]
        for face, person_id, score, message in candidates:
            if person_id is not None and labels.count(person_id) > 1:
                person_id = None
                message = 'Two faces matched the same identity. Please test each person separately.'
            person = people.get(person_id)
            live = False
            if person:
                if person_id in verified:
                    live, message = True, 'SFace identity and configured blink checks passed.'
                else:
                    live, message = biometrics.verify_liveness(db, person, face, config=config,
                                                              station_id='sface-test', test_state=blink_state)
                if live:
                    verified.add(person_id)
            results.append({'recognized': person is not None,
                            'person': {'id': person.id, 'full_name': person.full_name, 'role': person.role} if person else None,
                            'distance': None, 'identity_similarity': round(score, 4) if score is not None else None,
                            'quality_score': face.quality, 'box': face.box, 'presentation_verified': None,
                            'presentation_score': None, 'liveness_verified': live, 'message': message,
                            'camera_checks_passed': bool(person and live),
                            'attendance_event': {'recorded': False, 'test_mode': True}})
        for item in results:
            if item['person']:
                observed[item['person']['id']] = item
        max_matched = max(max_matched, sum(item['recognized'] for item in results))
    # This bounded test reports observations during this capture, never live presence or attendance.
    results = list(observed.values()) + [item for item in results if not item['person']]
    if not results:
        raise last_error or HTTPException(422, 'No clear face was available for SFace testing.')
    return {'matcher': 'SFace', 'result_scope': 'capture', 'results': results, 'face_count': len(results), 'frames_checked': checked,
            'max_faces_in_frame': maximum, 'max_identities_in_frame': max_matched, 'identity_comparisons': comparisons}
