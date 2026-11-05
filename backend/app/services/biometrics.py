from __future__ import annotations

import hashlib
import io
import json
import math
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath

import cv2
import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import BIOMETRIC_DIR, MODEL_DIR, settings
from ..models import BiometricAuditEvent, BiometricModel, BiometricSample, Person, RecognitionReview, User
from .settings_store import get_json
from .face_identity import embedding, feature_from_detection, MIN_SIMILARITY


FACE_SIZE = (200, 200)
MIN_BLUR_VARIANCE = 45.0
MIN_BRIGHTNESS = 35.0
MAX_BRIGHTNESS = 220.0
# Enrollment frames are a controlled single-person capture. Require stronger
# agreement than the cross-person gate cutoff before saving any face samples.
MIN_ENROLLMENT_SIMILARITY = 0.65
# Provisional fail-closed gate band above OpenCV's pairwise reference cutoff.
# Field calibration must measure false matches and missed matches before use.
MIN_GATE_SIMILARITY = MIN_SIMILARITY + 0.05
MIN_IDENTITY_MARGIN = 0.05
HUMAN_FACE_MODEL = Path(__file__).resolve().parents[2] / "resources" / "face_detection_yunet_2023mar.onnx"
HUMAN_FACE_MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


@dataclass
class ProcessedFace:
    image: np.ndarray
    encoded: bytes
    quality: float
    box: tuple[int, int, int, int] | None = None
    eye_count: int = 0
    face_signature: str = ""
    human_verified: bool = False
    presentation_score: float | None = None
    identity_feature: np.ndarray | None = None


class BiometricService:
    def __init__(self) -> None:
        self.fernet = Fernet(settings.encryption_key)
        self.detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        self.eye_detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml"))
        if self.detector.empty():
            raise RuntimeError("OpenCV Haar cascade could not be loaded")
        self._recognizer = None
        self._model_path = None
        self._lock = threading.RLock()
        self._enrollment_lock = threading.RLock()
        self._human_detector_lock = threading.RLock()
        self._human_detector = None
        self._liveness: dict[tuple[str, int], dict] = {}
        self._identity_cache = {}
        self._identity_lock = threading.RLock()

    def _decode(self, data: bytes) -> np.ndarray:
        array = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=422, detail="The uploaded frame is not a valid image")
        if image.shape[0] > 2160 or image.shape[1] > 3840:
            raise HTTPException(status_code=422, detail="Frame resolution is too large")
        return image

    def _processed_face(self, gray: np.ndarray, box: tuple[int, int, int, int], strict: bool) -> ProcessedFace:
        x, y, width, height = box
        margin_x, margin_y = int(width * 0.16), int(height * 0.20)
        x1, y1 = max(0, x - margin_x), max(0, y - margin_y)
        x2, y2 = min(gray.shape[1], x + width + margin_x), min(gray.shape[0], y + height + margin_y)
        face = cv2.resize(gray[y1:y2, x1:x2], FACE_SIZE, interpolation=cv2.INTER_AREA)
        blur = float(cv2.Laplacian(face, cv2.CV_64F).var())
        brightness = float(face.mean())
        if strict and blur < MIN_BLUR_VARIANCE:
            raise HTTPException(status_code=422, detail=f"Face is too blurry ({blur:.1f}); hold still and improve lighting")
        if strict and not MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS:
            raise HTTPException(status_code=422, detail=f"Face lighting is outside the accepted range ({brightness:.1f})")
        quality = min(100.0, (blur / 2.0)) * 0.7 + (100.0 - abs(128.0 - brightness) / 1.28) * 0.3
        ok, encoded = cv2.imencode(".png", face)
        if not ok:
            raise HTTPException(status_code=500, detail="Face crop could not be encoded")
        upper_face = face[:115, :]
        eyes = self.eye_detector.detectMultiScale(upper_face, scaleFactor=1.12, minNeighbors=5, minSize=(18, 18))
        tiny = cv2.resize(face, (16, 16), interpolation=cv2.INTER_AREA)
        signature_bits = (tiny > tiny.mean()).astype(np.uint8).tobytes()
        signature = hashlib.sha256(signature_bits).hexdigest()
        return ProcessedFace(face, encoded.tobytes(), round(max(0.0, min(100.0, quality)), 2),
                             tuple(map(int, box)), min(len(eyes), 2), signature)

    @staticmethod
    def _human_landmarks_valid(detection: np.ndarray) -> bool:
        if detection.shape != (15,) or not np.isfinite(detection).all():
            return False
        x, y, width, height = detection[:4]
        if width <= 0 or height <= 0 or detection[14] < 0.9:
            return False
        if not 0.55 <= width / height <= 1.3:
            return False
        eyes = sorted(detection[4:8].reshape(2, 2), key=lambda point: point[0])
        nose = detection[8:10]
        mouth = sorted(detection[10:14].reshape(2, 2), key=lambda point: point[0])
        for px, py in detection[4:14].reshape(5, 2):
            if not x < px < x + width or not y < py < y + height:
                return False
        eye_y = (eyes[0][1] + eyes[1][1]) / 2
        mouth_y = (mouth[0][1] + mouth[1][1]) / 2
        return bool(
            0.2 * width <= eyes[1][0] - eyes[0][0] <= 0.75 * width
            and abs(eyes[0][1] - eyes[1][1]) <= 0.15 * height
            and y + 0.15 * height < eye_y < y + 0.6 * height
            and eyes[0][0] < nose[0] < eyes[1][0]
            and eye_y + 0.05 * height < nose[1] < mouth_y
            and mouth_y > y + 0.5 * height
            and 0.12 * width <= mouth[1][0] - mouth[0][0] <= 0.7 * width
            and abs(mouth[0][1] - mouth[1][1]) <= 0.12 * height
        )

    def _human_detections(self, image: np.ndarray) -> np.ndarray:
        scale = min(1.0, 640 / max(image.shape[:2]))
        resized = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)))
        with self._human_detector_lock:
            if self._human_detector is None:
                try:
                    if hashlib.sha256(HUMAN_FACE_MODEL.read_bytes()).hexdigest() != HUMAN_FACE_MODEL_SHA256:
                        raise ValueError("Invalid detector model")
                    self._human_detector = cv2.FaceDetectorYN.create(str(HUMAN_FACE_MODEL), "", (320, 320), 0.9, 0.3, 5000)
                except (OSError, ValueError, cv2.error) as exc:
                    raise HTTPException(status_code=503, detail={
                        "code": "human_face_verifier_unavailable",
                        "message": "Human-face verification is unavailable. Restore the bundled face detector before using the camera.",
                    }) from exc
            try:
                self._human_detector.setInputSize((resized.shape[1], resized.shape[0]))
                _, detections = self._human_detector.detect(resized)
            except cv2.error as exc:
                raise HTTPException(status_code=503, detail="Human-face verification failed; use staff-assisted attendance") from exc
        if detections is None or len(detections) == 0:
            return np.empty((0, 15), dtype=np.float32)
        detections = detections.copy()
        detections[:, :14] /= scale
        return detections

    @staticmethod
    def _face_overlap(box: tuple[int, int, int, int], detection: np.ndarray) -> float:
        x, y, width, height = box
        dx, dy, dw, dh = detection[:4]
        overlap = max(0, min(x + width, dx + dw) - max(x, dx)) * max(0, min(y + height, dy + dh) - max(y, dy))
        union = width * height + dw * dh - overlap
        return float(overlap / union) if union > 0 else 0.0

    def process_faces(self, data: bytes, strict: bool = True, require_single: bool = False,
                      with_identity: bool = False) -> list[ProcessedFace]:
        image = self._decode(data)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        detections = self._human_detections(image)
        if with_identity:
            # SFace uses these verified landmarks; Haar must not discard a second valid human face.
            faces = [tuple(map(int, detection[:4])) for detection in detections
                     if self._human_landmarks_valid(detection) and detection[2] >= 70 and detection[3] >= 70]
        else:
            faces = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(70, 70))
        if len(faces) == 0:
            raise HTTPException(status_code=422, detail="No frontal human face was detected")
        if len(faces) > 10:
            raise HTTPException(status_code=422, detail="Too many faces are visible; process at most 10 people in one frame")
        if require_single and len(detections) > 1:
            raise HTTPException(status_code=422, detail="Only one human face may be visible during enrollment or a single-face scan")
        verified = [detection for detection in detections if self._human_landmarks_valid(detection)]
        processed: list[ProcessedFace] = []
        errors: list[str] = []
        for index, face_box in enumerate(sorted(faces, key=lambda item: int(item[0]))):
            try:
                overlaps = [self._face_overlap(face_box, detection) for detection in verified]
                if not overlaps or max(overlaps) < 0.4:
                    errors.append(f"Face {index + 1}: Human-face verification could not be completed")
                    continue
                # One verified detection must never authorize two candidate crops.
                detection = verified.pop(int(np.argmax(overlaps)))
                face = self._processed_face(gray, tuple(map(int, face_box)), strict)
                face.human_verified = True
                if with_identity:
                    face.identity_feature = feature_from_detection(image, detection)
                    # Keep the original color-frame identity template with the
                    # LBPH crop inside the same encrypted, integrity-checked file.
                    # Re-embedding the equalized grayscale crop changes SFace's input.
                    payload = io.BytesIO()
                    np.savez_compressed(payload, image=face.image, identity_feature=face.identity_feature)
                    face.encoded = payload.getvalue()
                processed.append(face)
            except HTTPException as exc:
                if exc.status_code >= 500:
                    raise
                errors.append(f"Face {index + 1}: {exc.detail}")
        if not processed:
            raise HTTPException(status_code=422, detail={
                "code": "human_face_required",
                "message": "Camera verification could not be completed. Try a clear frontal view or ask staff for assisted attendance. No attendance was recorded from this frame.",
                "rejected": errors,
            })
        return processed

    def process_frame(self, data: bytes, strict: bool = True, with_identity: bool = False) -> ProcessedFace:
        faces = self.process_faces(data, strict, require_single=True, with_identity=with_identity)
        if len(faces) > 1:
            raise HTTPException(status_code=422, detail="More than one face was detected; only one person may be enrolled at a time")
        return faces[0]

    def enrollment_snapshot(self, db: Session, person: Person) -> dict:
        samples = db.scalars(
            select(BiometricSample)
            .where(BiometricSample.person_id == person.id)
            .order_by(BiometricSample.created_at, BiometricSample.id)
        ).all()
        qualities = [sample.quality_score for sample in samples]
        return {
            "sample_count": len(samples),
            "enrolled": len(samples) >= settings.min_samples,
            "average_quality": round(sum(qualities) / len(qualities), 2) if qualities else None,
            "minimum_quality": round(min(qualities), 2) if qualities else None,
            "maximum_quality": round(max(qualities), 2) if qualities else None,
            "first_captured_at": samples[0].created_at.isoformat() if samples else None,
            "last_captured_at": samples[-1].created_at.isoformat() if samples else None,
        }

    def _audit(self, db: Session, person: Person, actor: User, action: str, reason: str,
               before: dict, after: dict, model_version: str | None) -> BiometricAuditEvent:
        event = BiometricAuditEvent(
            id=str(uuid.uuid4()), person_id=person.id, person_external_id=person.external_id,
            person_name=person.full_name, action=action, reason=reason.strip(), actor_user_id=actor.id,
            actor_name=actor.full_name, actor_role=actor.role,
            before_json=json.dumps(before, separators=(",", ":")),
            after_json=json.dumps(after, separators=(",", ":")), model_version=model_version,
        )
        db.add(event)
        return event

    def _stage_inactive_model_purge(self, db: Session) -> list[Path]:
        inactive = db.scalars(select(BiometricModel).where(BiometricModel.active.is_(False))).all()
        paths: list[Path] = []
        for record in inactive:
            paths.append(Path(record.file_path))
            db.delete(record)
        db.flush()
        return paths

    @staticmethod
    def _unlink_files(paths: list[Path]) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _deactivate_models(self, db: Session) -> None:
        db.execute(update(BiometricModel).values(active=False))
        db.flush()
        with self._lock:
            self._recognizer = None
            self._model_path = None

    def purge_obsolete_models(self, db: Session) -> int:
        """Remove legacy inactive LBPH rows and their encrypted files."""
        paths = self._stage_inactive_model_purge(db)
        db.commit()
        self._unlink_files(paths)
        return len(paths)

    def enroll(self, db: Session, person: Person, frames: list[bytes], actor: User, reason: str,
               require_existing: bool | None = None) -> dict:
        # Keep duplicate checking and persistence together, including across
        # PostgreSQL workers. The advisory lock ends with the transaction.
        with self._enrollment_lock:
            if db.get_bind().dialect.name == "postgresql":
                if not db.scalar(select(func.pg_try_advisory_xact_lock(1950508110))):
                    raise HTTPException(status_code=409, detail="Another facial enrollment is in progress; try again when it finishes")
            return self._enroll(db, person, frames, actor, reason, require_existing)

    def _identity_feature(self, image):
        return embedding(image, self)

    def _identity_gallery(self, db, include_inactive=False, exclude_person_id=None,
                          missing_person_ids: set[int] | None = None):
        query = select(BiometricSample).join(Person).where(Person.biometric_consent.is_(True))
        if not include_inactive:
            query = query.where(Person.active.is_(True))
        if exclude_person_id is not None:
            query = query.where(Person.id != exclude_person_id)
        samples = db.scalars(query.order_by(BiometricSample.person_id, BiometricSample.id)).all()
        gallery, refreshed = [], {}
        with self._identity_lock:
            for sample in samples:
                key = (sample.id, sample.person_id, sample.sha256)
                try:
                    if missing_person_ids is not None and not self._sample_path(sample).is_file():
                        raise FileNotFoundError('Enrollment sample is missing')
                    feature = self._identity_cache.get(key)
                    if feature is None:
                        feature = self._load_sample_identity_feature(sample)
                except HTTPException as error:
                    # LBPH samples are tight face crops. Some valid crops cannot be
                    # re-detected by YuNet after reload, even though they were
                    # verified from the original camera frame during enrollment.
                    # Skip only that unusable SFace reference; other storage,
                    # integrity, and verifier failures must still fail closed.
                    if error.status_code == 422:
                        continue
                    raise HTTPException(503, detail={
                        'code': 'identity_verifier_unavailable',
                        'message': 'An existing face enrollment cannot be verified. No identity was accepted; use staff assistance.',
                    }) from error
                except FileNotFoundError as error:
                    if missing_person_ids is not None:
                        missing_person_ids.add(sample.person_id)
                        continue
                    owner = db.get(Person, sample.person_id)
                    raise HTTPException(503, detail={
                        'code': 'identity_verifier_unavailable',
                        'message': f'The saved face files for {owner.full_name} are missing on this computer. Their face enrollment needs recovery before gate recognition can resume.',
                        'recovery_person_id': owner.id,
                        'recovery_person_name': owner.full_name,
                    }) from error
                except (OSError, RuntimeError, ValueError, InvalidToken, cv2.error) as error:
                    raise HTTPException(503, detail={
                        'code': 'identity_verifier_unavailable',
                        'message': 'An existing face enrollment cannot be verified. No identity was accepted; use staff assistance.',
                    }) from error
                refreshed[key] = feature
                gallery.append((sample.person_id, feature))
            self._identity_cache = refreshed
        reference_counts = {}
        for person_id, _feature in gallery:
            reference_counts[person_id] = reference_counts.get(person_id, 0) + 1
        people_without_references = {sample.person_id for sample in samples if reference_counts.get(sample.person_id, 0) < 3}
        if people_without_references - (missing_person_ids or set()):
            raise HTTPException(503, detail={
                'code': 'identity_verifier_unavailable',
                'message': 'At least one enrolled person has fewer than three usable SFace references. Ask an administrator to re-enroll that person before recognition.',
            })
        references_by_person = {}
        for person_id, feature in gallery:
            references_by_person.setdefault(person_id, []).append(feature)
        if any(np.any(np.stack(features) @ np.stack(features).T < MIN_ENROLLMENT_SIMILARITY)
               for features in references_by_person.values()):
            raise HTTPException(503, detail={
                'code': 'identity_verifier_unavailable',
                'message': 'An existing face enrollment contains inconsistent identity references. Ask an administrator to re-enroll that person before recognition.',
            })
        return samples, gallery

    def _recognition_gallery(self, db: Session) -> tuple[list, set[int]]:
        missing_person_ids: set[int] = set()
        _samples, gallery = self._identity_gallery(db, missing_person_ids=missing_person_ids)
        # Exclude the entire affected identity, including cached/readable
        # references. A partial enrollment must never identify that person.
        gallery = [(person_id, feature) for person_id, feature in gallery
                   if person_id not in missing_person_ids]
        if not gallery:
            raise HTTPException(409, detail={
                'code': 'no_local_identity_references',
                'message': 'No complete local face enrollments are available. Enroll a person on this computer or restore their samples; use assisted attendance in the meantime.',
            })
        return gallery, missing_person_ids

    def _identity_scores(self, image, gallery, feature=None):
        feature = self._identity_feature(image) if feature is None else feature
        if not gallery:
            return []
        person_ids, references = zip(*gallery)
        similarities = np.clip(np.stack(references) @ feature, -1, 1)
        unique_ids, slots = np.unique(person_ids, return_inverse=True)
        # The third-best stored sample must clear the identity cutoff.
        # A single accidental nearest neighbor becomes more likely as the
        # gallery grows; one matching sample must never decide attendance.
        corroborated = np.full(len(unique_ids), -1.0)
        for index in range(len(unique_ids)):
            own_scores = similarities[slots == index]
            if len(own_scores) >= 3:
                corroborated[index] = np.partition(own_scores, -3)[-3]
        return sorted(zip(unique_ids.tolist(), corroborated.tolist()), key=lambda item: item[1], reverse=True)

    def _check_duplicate_enrollment(self, db: Session, person: Person,
                                    accepted: list[ProcessedFace]) -> dict:
        missing_person_ids: set[int] = set()
        samples, gallery = self._identity_gallery(db, include_inactive=True, exclude_person_id=person.id,
                                                 missing_person_ids=missing_person_ids)
        exact_hashes = {sample.sha256: sample.person_id for sample in samples}
        votes = {}
        for processed in accepted:
            duplicate_id = exact_hashes.get(hashlib.sha256(processed.encoded).hexdigest())
            if duplicate_id is None:
                for candidate_id, score in self._identity_scores(processed.image, gallery, processed.identity_feature):
                    if score >= MIN_SIMILARITY:
                        votes[candidate_id] = votes.get(candidate_id, 0) + 1
                        if votes[candidate_id] >= 3:
                            duplicate_id = candidate_id
                            break
            if duplicate_id is not None:
                owner = db.get(Person, duplicate_id)
                raise HTTPException(409, detail={
                    'code': 'duplicate_face',
                    'message': f"This face matches the existing enrollment for {owner.full_name} ({owner.external_id}). Use that person's existing enrollment or capture the correct person's face.",
                    'existing_person_id': duplicate_id,
                })
        return {'status': 'incomplete' if missing_person_ids else 'complete',
                'missing_person_ids': sorted(missing_person_ids)}

    def validate_enrollment_frames(self, frames: list[bytes], diagnostics: dict | None = None) -> tuple[list[ProcessedFace], list[str]]:
        if not settings.biometric_enabled:
            raise HTTPException(status_code=503, detail="Biometric processing is disabled by server configuration")
        accepted: list[ProcessedFace] = []
        rejected: list[str] = []
        hashes: set[str] = set()
        if diagnostics is not None:
            diagnostics.update(photo_video_protection_enabled=False)
        for index, frame in enumerate(frames):
            try:
                processed = self.process_frame(frame, strict=True, with_identity=True)
                if not processed.human_verified:
                    raise HTTPException(status_code=422, detail="A verified human face is required for every enrollment frame")
                digest = hashlib.sha256(processed.image.tobytes()).hexdigest()
                if digest in hashes:
                    rejected.append(f"Frame {index + 1}: duplicate crop")
                    continue
                hashes.add(digest)
                accepted.append(processed)
            except HTTPException as exc:
                if exc.status_code >= 500:
                    raise
                detail = exc.detail.get("message", str(exc.detail)) if isinstance(exc.detail, dict) else exc.detail
                rejected.append(f"Frame {index + 1}: {detail}")
        if len(accepted) < settings.min_samples:
            raise HTTPException(status_code=422, detail={"message": f"Only {len(accepted)} quality frames were accepted; at least {settings.min_samples} are required", "rejected": rejected})

        # A capture burst must contain one identity throughout. A stranger who
        # enters the frame before enrollment is saved must not become a sample
        # of this person's face, even when that stranger is not yet enrolled.
        features = np.stack([face.identity_feature if face.identity_feature is not None
                             else self._identity_feature(face.image) for face in accepted])
        similarities = features @ features.T
        if np.any(similarities < MIN_ENROLLMENT_SIMILARITY):
            raise HTTPException(status_code=422, detail={
                'code': 'mixed_enrollment_faces',
                'message': 'The enrollment frames do not consistently show one person. Clear the camera area and capture this person again.',
            })

        # Gate matching reloads the saved templates. Check that this same path can
        # recover enough references before writing samples or a trained model.
        usable_references = []
        for face in accepted:
            try:
                stored_image, stored_feature = self._decode_sample(face.encoded)
                if stored_feature is None:
                    stored_feature = self._identity_feature(stored_image)
            except HTTPException as error:
                if error.status_code == 422:
                    continue
                raise
            if float(stored_feature @ features[0]) < MIN_ENROLLMENT_SIMILARITY:
                raise HTTPException(status_code=422, detail={
                    'code': 'inconsistent_identity_references',
                    'message': 'A saved face crop would not match the captured person. Capture a new clear set of frames.',
                })
            usable_references.append(stored_feature)
        if len(usable_references) < 3:
            raise HTTPException(status_code=422, detail={
                'code': 'insufficient_identity_references',
                'message': 'Too few saved face crops can be used for reliable recognition. Face the camera directly and capture again.',
            })
        stored_similarities = np.stack(usable_references) @ np.stack(usable_references).T
        if np.any(stored_similarities < MIN_ENROLLMENT_SIMILARITY):
            raise HTTPException(status_code=422, detail={
                'code': 'inconsistent_identity_references',
                'message': 'The saved face crops do not agree on one identity. Capture a new clear set of frames.',
            })

        return accepted, rejected

    def _enroll(self, db: Session, person: Person, frames: list[bytes], actor: User, reason: str,
                require_existing: bool | None = None) -> dict:
        if not settings.biometric_enabled:
            raise HTTPException(status_code=503, detail="Biometric processing is disabled by server configuration")
        if not person.biometric_consent:
            raise HTTPException(status_code=422, detail="Documented biometric consent/authorization is required before enrollment")
        reason = reason.strip()
        if len(reason) < 8:
            raise HTTPException(status_code=422, detail="A specific reason of at least 8 characters is required")
        existing = db.scalars(select(BiometricSample).where(BiometricSample.person_id == person.id)).all()
        if require_existing is True and not existing:
            raise HTTPException(status_code=404, detail="This person does not have a facial enrollment to update")
        if require_existing is False and existing:
            raise HTTPException(status_code=409, detail="This person is already enrolled; use re-enrollment to replace the face samples")
        accepted, rejected = self.validate_enrollment_frames(frames)
        duplicate_check = self._check_duplicate_enrollment(db, person, accepted)
        before = self.enrollment_snapshot(db, person)
        action = "updated" if existing else "created"
        person_dir = BIOMETRIC_DIR / f"person_{person.id}"
        person_dir.mkdir(parents=True, exist_ok=True)
        old_paths = [Path(sample.encrypted_path) for sample in existing]
        new_paths: list[Path] = []
        obsolete_model_paths: list[Path] = []
        model = None
        try:
            for old in existing:
                db.delete(old)
            db.flush()
            for processed in accepted:
                sample_id = str(uuid.uuid4())
                encrypted = self.fernet.encrypt(processed.encoded)
                target = person_dir / f"{sample_id}.enc"
                target.write_bytes(encrypted)
                new_paths.append(target)
                db.add(BiometricSample(
                    id=sample_id,
                    person_id=person.id,
                    encrypted_path=str(target),
                    sha256=hashlib.sha256(processed.encoded).hexdigest(),
                    quality_score=processed.quality,
                ))
            db.flush()
            model = self.train(db, commit=False, missing_person_ids=set(duplicate_check['missing_person_ids']))
            after = self.enrollment_snapshot(db, person)
            if duplicate_check['status'] == 'incomplete':
                after['duplicate_check'] = duplicate_check
            self._audit(db, person, actor, action, reason, before, after, model["version"])
            obsolete_model_paths = self._stage_inactive_model_purge(db)
            db.commit()
        except Exception:
            db.rollback()
            for path in new_paths:
                path.unlink(missing_ok=True)
            if model:
                self._unlink_files([MODEL_DIR / f"lbph-{model['version']}.yml.enc"])
            with self._lock:
                self._recognizer = None
                self._model_path = None
            raise
        self._unlink_files(old_paths + obsolete_model_paths)
        warnings = []
        if duplicate_check['status'] == 'incomplete':
            warnings.append('Enrollment saved for this person. Some older face files are missing, so duplicate checks against those records are incomplete. Affected older enrollments are unavailable for gate matching until recovered; complete local enrollments remain usable.')
        return {"action": action, "accepted": len(accepted), "rejected": rejected, "enrollment": after,
                "model": model, "duplicate_check": duplicate_check, "warnings": warnings}

    def delete_enrollment(self, db: Session, person: Person, actor: User, reason: str) -> dict:
        with self.deleting_enrollment(db, person, actor, reason) as result:
            db.commit()
        return result

    @contextmanager
    def deleting_enrollment(self, db: Session, person: Person, actor: User, reason: str):
        # The caller commits its entire operation before file cleanup is allowed.
        with self._enrollment_lock:
            if db.get_bind().dialect.name == "postgresql":
                if not db.scalar(select(func.pg_try_advisory_xact_lock(1950508110))):
                    raise HTTPException(status_code=409, detail="Another facial enrollment is in progress; try again when it finishes")
            with self._deleting_enrollment(db, person, actor, reason) as result:
                yield result

    @contextmanager
    def _deleting_enrollment(self, db: Session, person: Person, actor: User, reason: str):
        reason = reason.strip()
        if len(reason) < 8:
            raise HTTPException(status_code=422, detail="A specific deletion reason of at least 8 characters is required")
        samples = db.scalars(select(BiometricSample).where(BiometricSample.person_id == person.id)).all()
        if not samples:
            raise HTTPException(status_code=404, detail="This person does not have a facial enrollment")
        before = self.enrollment_snapshot(db, person)
        old_paths = [self._sample_path(sample) for sample in samples]
        obsolete_model_paths: list[Path] = []
        model = None
        try:
            for sample in samples:
                db.delete(sample)
            db.flush()
            remaining = db.scalar(select(func.count(BiometricSample.id))) or 0
            model = self.train(db, commit=False) if remaining else None
            if not remaining:
                self._deactivate_models(db)
            after = self.enrollment_snapshot(db, person)
            self._audit(db, person, actor, "deleted", reason, before, after,
                        model["version"] if model else None)
            obsolete_model_paths = self._stage_inactive_model_purge(db)
            result = {"deleted": True, "removed_samples": before["sample_count"],
                      "removed_model_records": len(obsolete_model_paths), "enrollment": after, "model": model}
            yield result
        except Exception:
            db.rollback()
            if model:
                self._unlink_files([MODEL_DIR / f"lbph-{model['version']}.yml.enc"])
            with self._lock:
                self._recognizer = None
                self._model_path = None
            raise
        self._unlink_files(old_paths + obsolete_model_paths)
        with self._identity_lock:
            self._identity_cache = {key: feature for key, feature in self._identity_cache.items() if key[1] != person.id}
        result["file_cleanup_pending"] = sum(path.exists() for path in old_paths + obsolete_model_paths)
        try:
            (BIOMETRIC_DIR / f"person_{person.id}").rmdir()
        except OSError:
            pass

    @staticmethod
    def _sample_path(sample: BiometricSample) -> Path:
        path = Path(sample.encrypted_path)
        if not path.is_file():
            path = BIOMETRIC_DIR / f"person_{sample.person_id}" / PureWindowsPath(sample.encrypted_path).name
        return path

    def _load_sample_data(self, sample: BiometricSample) -> bytes:
        path = self._sample_path(sample)
        encrypted = path.read_bytes()
        raw = self.fernet.decrypt(encrypted)
        if hashlib.sha256(raw).hexdigest() != sample.sha256:
            raise RuntimeError(f"Stored sample {sample.id} failed its integrity check")
        return raw

    @staticmethod
    def _decode_sample(raw: bytes) -> tuple[np.ndarray, np.ndarray | None]:
        if raw.startswith(b'PK'):
            with np.load(io.BytesIO(raw), allow_pickle=False) as payload:
                image = payload['image'].copy()
                feature = payload['identity_feature'].copy()
            if image.shape != FACE_SIZE or image.dtype != np.uint8:
                raise ValueError('Invalid stored face crop')
            if (feature.shape != (128,) or not np.isfinite(feature).all()
                    or not np.isclose(np.linalg.norm(feature), 1.0, atol=1e-5)):
                raise ValueError('Invalid stored identity feature')
            return image, feature
        # Existing PNG enrollments remain readable without a data migration.
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise RuntimeError('Stored face sample cannot be decoded')
        return image, None

    def _load_sample_image(self, sample: BiometricSample) -> np.ndarray:
        return self._decode_sample(self._load_sample_data(sample))[0]

    def _load_sample_identity_feature(self, sample: BiometricSample, legacy_embedding=None) -> np.ndarray:
        image, feature = self._decode_sample(self._load_sample_data(sample))
        if feature is not None:
            return feature
        return self._identity_feature(image) if legacy_embedding is None else legacy_embedding(image, self)

    def train(self, db: Session, commit: bool = True, missing_person_ids: set[int] | None = None) -> dict:
        samples = db.scalars(
            select(BiometricSample)
            .join(Person)
            .where(Person.active.is_(True), Person.biometric_consent.is_(True))
            .order_by(BiometricSample.person_id, BiometricSample.created_at)
        ).all()
        if not samples:
            raise HTTPException(status_code=422, detail="No authorized biometric samples are available for training")
        images, usable_samples = [], []
        for sample in samples:
            try:
                image = self._load_sample_image(sample)
            except FileNotFoundError:
                # Enrollment may proceed independently of known missing older
                # records. Never discard their metadata or ignore corrupt files.
                if sample.person_id in (missing_person_ids or set()):
                    continue
                raise
            images.append(image)
            usable_samples.append(sample)
        if not usable_samples:
            raise HTTPException(422, detail='No readable authorized biometric samples are available for training')
        samples = usable_samples
        labels = np.array([sample.person_id for sample in samples], dtype=np.int32)
        recognizer = cv2.face.LBPHFaceRecognizer_create(1, 8, 8, 8, settings.lbph_threshold)
        recognizer.train(images, labels)
        version = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
        model_path = MODEL_DIR / f"lbph-{version}.yml.enc"
        temporary = MODEL_DIR / f"lbph-{version}.tmp.yml"
        recognizer.write(str(temporary))
        plaintext = temporary.read_bytes()
        temporary.unlink(missing_ok=True)
        encrypted_model = self.fernet.encrypt(plaintext)
        encrypted_temporary = MODEL_DIR / f"lbph-{version}.tmp.enc"
        encrypted_temporary.write_bytes(encrypted_model)
        os.replace(encrypted_temporary, model_path)
        digest = hashlib.sha256(encrypted_model).hexdigest()
        db.execute(update(BiometricModel).values(active=False))
        person_count = len(set(labels.tolist()))
        record = BiometricModel(
            version=version, file_path=str(model_path), sha256=digest,
            threshold=settings.lbph_threshold, person_count=person_count,
            sample_count=len(samples), active=True,
        )
        db.add(record)
        obsolete_model_paths: list[Path] = []
        if commit:
            db.flush()
            obsolete_model_paths = self._stage_inactive_model_purge(db)
            db.commit()
        else:
            db.flush()
        with self._lock:
            self._recognizer = recognizer
            self._model_path = str(model_path)
        if commit:
            self._unlink_files(obsolete_model_paths)
        return {"version": version, "sha256": digest, "person_count": person_count, "sample_count": len(samples), "threshold": settings.lbph_threshold}

    def _active_recognizer(self, db: Session):
        active = db.scalar(select(BiometricModel).where(BiometricModel.active.is_(True)).order_by(BiometricModel.id.desc()))
        if not active:
            raise HTTPException(status_code=409, detail={"code": "model_not_trained", "message": "No trained face model is available. Enroll an authorized person and train the model first."})
        model_path = Path(active.file_path)
        if not model_path.is_file():
            model_path = MODEL_DIR / PureWindowsPath(active.file_path).name
        if not model_path.is_file():
            raise HTTPException(status_code=409, detail={"code": "model_file_missing", "message": "The trained model is registered in the database, but its encrypted file is missing on this computer. Restore the model, enrollment files, and matching encryption key from the computer that captured the faces, or ask the administrator to rebuild the face enrollments here."})
        with self._lock:
            if self._recognizer is None or self._model_path != str(model_path):
                recognizer = cv2.face.LBPHFaceRecognizer_create()
                encrypted = model_path.read_bytes()
                if hashlib.sha256(encrypted).hexdigest() != active.sha256:
                    raise HTTPException(status_code=409, detail={"code": "model_integrity_failed", "message": "The trained face model failed its integrity check. Restore the matching model file before recognition."})
                temporary = MODEL_DIR / f"load-{os.getpid()}-{threading.get_ident()}.yml"
                try:
                    temporary.write_bytes(self.fernet.decrypt(encrypted))
                    recognizer.read(str(temporary))
                except InvalidToken as exc:
                    raise HTTPException(status_code=409, detail={"code": "model_key_mismatch", "message": "The face model cannot be decrypted with this computer's encryption key. Restore its matching key through the administrator's recovery process."}) from exc
                except cv2.error as exc:
                    raise HTTPException(status_code=409, detail={"code": "model_unreadable", "message": "The face model cannot be loaded. Restore its matching model file or retrain from readable, authorized samples."}) from exc
                finally:
                    temporary.unlink(missing_ok=True)
                self._recognizer = recognizer
                self._model_path = str(model_path)
            return self._recognizer, active

    def model_readiness(self, db: Session) -> dict:
        try:
            self._active_recognizer(db)
            _gallery, missing_person_ids = self._recognition_gallery(db)
            if missing_person_ids:
                return {'available': True, 'code': 'ready_with_missing_enrollments',
                        'message': f'Recognition is ready for complete local enrollments. {len(missing_person_ids)} older enrollment(s) have missing files and cannot be matched. Use assisted attendance for those people until their samples are restored.'}
            return {"available": True, "code": "ready", "message": "Trained face model is ready on this computer."}
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"code": "model_unavailable", "message": str(exc.detail)}
            return {"available": False, **detail}
        except OSError:
            return {"available": False, "code": "model_file_unreadable", "message": "The trained model file could not be read on this computer. Check file access and restore its encrypted files."}

    @staticmethod
    def runtime_config(db: Session) -> dict:
        value = get_json(db, "biometric.runtime", {})
        return {
            "threshold": float(value.get("threshold", settings.lbph_threshold)),
            "liveness_enabled": bool(value.get("liveness_enabled", True)),
            "liveness_window_seconds": int(value.get("liveness_window_seconds", 8)),
            "review_failure_threshold": int(value.get("review_failure_threshold", 4)),
        }

    def verify_liveness(self, db: Session, person: Person, processed: ProcessedFace,
                        config: dict | None = None, station_id: str = 'default', test_state: dict | None = None) -> tuple[bool, str]:
        config = config if config is not None else self.runtime_config(db)
        if not config["liveness_enabled"]:
            return True, "Liveness verification is disabled by an authorized administrator"
        now = datetime.utcnow()
        states = self._liveness if test_state is None else test_state
        key = (station_id, person.id)
        state = states.get(key)
        if not state or state["expires_at"] < now:
            for expired_key in [key for key, value in states.items() if value["expires_at"] < now]:
                states.pop(expired_key)
            state = {"stage": "open" if processed.eye_count else "waiting_open",
                     "expires_at": now + timedelta(seconds=config["liveness_window_seconds"])}
            states[key] = state
            return False, "Liveness check: face the camera, open your eyes, then blink once. Staff assistance is available if needed."
        if state["stage"] == "waiting_open" and processed.eye_count > 0:
            state["stage"] = "open"
        if state["stage"] == "open" and processed.eye_count == 0:
            state["stage"] = "closed"
            return False, "Blink detected; open your eyes and face the camera to complete verification"
        if state["stage"] == "closed" and processed.eye_count > 0:
            states.pop(key, None)
            if test_state is not None:
                return True, "Natural blink sequence verified (test only)"
            signature = hashlib.sha256(f"person:{person.id}".encode()).hexdigest()
            pending = db.scalar(select(RecognitionReview).where(
                RecognitionReview.face_signature == signature,
                RecognitionReview.review_type == "Liveness",
                RecognitionReview.status.in_(["Open", "Observing"]),
            ).order_by(RecognitionReview.last_seen_at.desc()))
            if pending:
                pending.status = "Resolved"
                pending.resolution_note = "Liveness challenge completed at the gate station"
                pending.resolved_by_name = "EduScan liveness verifier"
                pending.resolved_at = now
                db.commit()
            return True, "Natural blink sequence verified"
        return False, "Liveness check is waiting for a blink; keep your face visible"

    @staticmethod
    def record_review(db: Session, processed: ProcessedFace, review_type: str, reason: str,
                      person: Person | None, distance: float) -> RecognitionReview:
        now = datetime.utcnow()
        signature = hashlib.sha256(f"person:{person.id}".encode()).hexdigest() if person else processed.face_signature
        item = db.scalar(select(RecognitionReview).where(
            RecognitionReview.face_signature == signature,
            RecognitionReview.review_type == review_type,
            RecognitionReview.status.in_(["Open", "Observing"]),
            RecognitionReview.last_seen_at >= now - timedelta(minutes=2),
        ).order_by(RecognitionReview.last_seen_at.desc()))
        if item:
            item.occurrence_count += 1
            item.last_seen_at = now
            item.distance = distance
            item.quality_score = processed.quality
            item.reason = reason
            if review_type == "Liveness" and item.occurrence_count >= BiometricService.runtime_config(db)["review_failure_threshold"]:
                item.status = "Open"
        else:
            initial_status = "Observing" if review_type == "Liveness" and BiometricService.runtime_config(db)["review_failure_threshold"] > 1 else "Open"
            item = RecognitionReview(
                id=str(uuid.uuid4()), face_signature=signature,
                candidate_person_id=person.id if person else None,
                candidate_name=person.full_name if person else None,
                review_type=review_type, reason=reason, distance=distance,
                quality_score=processed.quality, occurrence_count=1, status=initial_status,
            )
            db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def recognize_many(self, db: Session, frame: bytes) -> list[dict]:
        return self.recognize_frames(db, [frame])

    def recognize_frames(self, db: Session, frames: list[bytes], verified_present: set[int] | None = None,
                         require_single: bool = False, station_id: str = 'default', diagnostics: dict | None = None) -> list[dict]:
        """Check a short camera burst with one model/configuration/identity lookup."""
        if not settings.biometric_enabled:
            raise HTTPException(status_code=503, detail="Biometric processing is disabled by server configuration")
        config = None
        recognizer = None
        gallery = None
        completed_blinks = set()
        people = {}
        matches = {}
        collided_labels = set()
        conflicted_labels = set()
        observed_features = []
        unknown = []
        last_error = None
        empty_frames = 0
        test_state = {} if diagnostics is not None else None
        verified_present = (verified_present or set()) if diagnostics is None else set()
        if diagnostics is not None:
            diagnostics.update(matcher='SFace', frames_checked=0, max_faces_in_frame=0, identity_comparisons=[])
        for frame in frames:
            try:
                processed_faces = self.process_faces(frame, strict=True, require_single=require_single, with_identity=True)
            except HTTPException as error:
                if error.status_code != 422:
                    raise
                last_error = error
                if error.detail == 'No frontal human face was detected':
                    empty_frames += 1
                unknown = []
                if diagnostics is not None:
                    diagnostics['identity_comparisons'] = []
                continue
            if diagnostics is not None:
                diagnostics['frames_checked'] += 1
                diagnostics['max_faces_in_frame'] = max(diagnostics['max_faces_in_frame'], len(processed_faces))
                diagnostics['identity_comparisons'] = []
            if len(processed_faces) > 5:
                raise HTTPException(status_code=422, detail='Too many faces are visible; process at most 5 people in one frame')
            if recognizer is None:
                recognizer, _model = self._active_recognizer(db)
                config = self.runtime_config(db)
                gallery, missing_person_ids = self._recognition_gallery(db)
                if diagnostics is not None:
                    diagnostics['unavailable_person_ids'] = sorted(missing_person_ids)
            current_matches = {}
            unknown = []
            predictions = []
            for processed in processed_faces:
                feature = processed.identity_feature if processed.identity_feature is not None else self._identity_feature(processed.image)
                try:
                    ranked = self._identity_scores(processed.image, gallery, feature)
                except HTTPException as error:
                    if error.status_code != 422:
                        raise
                    ranked = []
                qualified = [key for key, score in ranked if score >= MIN_GATE_SIMILARITY]
                near_tie = len(ranked) > 1 and ranked[0][1] - ranked[1][1] < MIN_IDENTITY_MARGIN
                label = qualified[0] if len(qualified) == 1 and not near_tie else -1
                collector = cv2.face.StandardCollector_create(float('inf'))
                with self._lock:
                    recognizer.predict_collect(processed.image, collector)
                # Retain the existing LBPH audit distance, but never use it to choose the identity.
                distances = [(int(key), float(value)) for key, value in collector.getResults() if math.isfinite(value)]
                selected = [value for key, value in distances if label == -1 or key == label]
                distance = min(selected) if selected else 1e9
                predictions.append((label, distance, ranked, len(qualified) > 1 or near_tie, feature))
            valid_labels = [label for label, _, _, _, _ in predictions if label != -1]
            collided_labels.update(label for label in valid_labels if valid_labels.count(label) > 1)
            for label, _, _, _, feature in predictions:
                for prior_label, prior_feature in observed_features:
                    similarity = float(feature @ prior_feature)
                    if label == prior_label and label != -1 and similarity < MIN_SIMILARITY:
                        conflicted_labels.add(label)
                    elif similarity >= MIN_SIMILARITY and label != prior_label:
                        conflicted_labels.update(person_id for person_id in (label, prior_label) if person_id != -1)
                observed_features.append((label, feature))
            for label in collided_labels | conflicted_labels:
                matches.pop(label, None)
            for processed, (label, distance, ranked, ambiguous, _) in zip(processed_faces, predictions):
                if diagnostics is not None:
                    comparison = []
                    for candidate_id, similarity in ranked[:2]:
                        if candidate_id not in people:
                            people[candidate_id] = db.get(Person, candidate_id)
                        candidate = people[candidate_id]
                        if candidate:
                            comparison.append({'name': candidate.full_name, 'similarity': round(similarity, 4)})
                    diagnostics['identity_comparisons'].append({'face': len(diagnostics['identity_comparisons']) + 1,
                                                               'threshold': MIN_GATE_SIMILARITY, 'candidates': comparison})
                person = None
                collision = label in collided_labels or label in conflicted_labels
                if label != -1 and not collision:
                    if label not in people:
                        people[label] = db.get(Person, label)
                    candidate = people[label]
                    if candidate and candidate.active and candidate.biometric_consent:
                        person = candidate
                live = False
                message = ('Identity changed or conflicted during this capture. Please scan separately and verify with staff.'
                           if label in conflicted_labels else 'Two faces matched the same identity. Please scan separately so each person can be verified.'
                           if collision else 'This face resembles multiple enrollments; identity is uncertain.' if ambiguous else 'Face was not recognized with sufficient confidence')
                if person:
                    # Keep a completed blink verified for the rest of this burst.
                    if person.id in verified_present:
                        live, message = True, 'Attendance already recorded for this visit'
                    elif person.id in completed_blinks:
                        live, message = True, 'Identity and configured blink checks verified'
                    else:
                        with self._lock:
                            live, message = self.verify_liveness(db, person, processed, config=config, station_id=station_id, test_state=test_state)
                if person and live:
                    completed_blinks.add(person.id)
                match = {'identity_similarity': ranked[0][1] if ranked else None, 'person': person, 'distance': float(distance), 'quality': processed.quality,
                         'box': processed.box, 'face_signature': processed.face_signature,
                         'eye_count': processed.eye_count, 'liveness_verified': live,
                         'presentation_verified': None, 'presentation_score': None,
                         'message': message, 'review_id': None, '_processed': processed}
                if person:
                    current_matches[person.id] = match
                else:
                    unknown.append(match)
            # Keep each distinct person seen in this burst, even if the final frame misses them.
            matches.update(current_matches)
        results = list(matches.values()) + unknown
        if not results:
            if empty_frames == len(frames):
                raise HTTPException(status_code=422, detail={'code': 'no_faces_in_burst',
                                                            'message': 'No frontal human face was detected'})
            raise last_error or HTTPException(status_code=422, detail='No frontal human face was detected')
        # Audit only the final outcome, rather than writing on every blink frame.
        for match in results:
            processed = match.pop('_processed')
            if diagnostics is None and (not match['person'] or not match['liveness_verified']):
                review = self.record_review(db, processed, 'Liveness' if match['person'] else 'Unknown Face',
                                            match['message'], match['person'], match['distance'])
                match['review_id'] = review.id
        return results



biometric_service = BiometricService()
