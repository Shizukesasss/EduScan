"""Shared local SFace identity features; no image or feature persistence."""
import hashlib
import threading
from pathlib import Path
import cv2
import numpy as np
from fastapi import HTTPException

MODEL = Path(__file__).resolve().parents[2] / 'resources' / 'face_recognition_sface_2021dec.onnx'
MODEL_SHA256 = '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79'
# OpenCV's reference cosine cutoff; fresh camera and unknown-person validation are still required.
MIN_SIMILARITY = 0.363
_lock = threading.RLock()
_network = None


def embedding(gray, biometrics):
    image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    detections = biometrics._human_detections(image)
    if len(detections) != 1 or not biometrics._human_landmarks_valid(detections[0]):
        raise HTTPException(422, 'SFace could not align one clear face. Face the camera directly and retry.')
    return feature_from_detection(image, detections[0])


def feature_from_detection(image, detection):
    """Align one already human-verified detection in the original color frame."""
    global _network
    with _lock:
        try:
            if _network is None:
                if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
                    raise ValueError('Model integrity check failed')
                _network = cv2.FaceRecognizerSF_create(str(MODEL), '')
            aligned = _network.alignCrop(image, detection)
            feature = _network.feature(aligned).copy().reshape(-1)
            norm = np.linalg.norm(feature)
            if feature.size != 128 or not np.isfinite(feature).all() or not np.isfinite(norm) or norm <= 0:
                raise ValueError('Invalid identity feature')
            return feature / norm
        except (OSError, ValueError, cv2.error) as error:
            raise HTTPException(503, detail={
                'code': 'identity_verifier_unavailable',
                'message': 'Face identity verification is unavailable. No identity was accepted; use staff assistance while the verifier is restored.',
            }) from error


