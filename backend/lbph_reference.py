"""
EduScan LBPH Face Recognition — Standalone Reference Implementation
====================================================================

Demonstrates every best practice for LBPH-based recognition:
  1. Webcam capture of training images with guided poses
  2. Full preprocessing pipeline (CLAHE, gamma, alignment, unsharp mask)
  3. LBPH training with tuned parameters (radius=2, neighbors=16)
  4. Real-time recognition with confidence display and rejection threshold
  5. Model save/load for persistence

Requirements:
  pip install opencv-contrib-python numpy

Usage:
  python lbph_reference.py enroll "Juan dela Cruz"    # Capture 50 frames
  python lbph_reference.py enroll "Maria Santos"      # Capture another person
  python lbph_reference.py train                       # Train the model
  python lbph_reference.py recognize                   # Live recognition
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FACE_SIZE = (200, 200)             # All crops are resized to this
SAMPLES_PER_PERSON = 50            # Number of frames to capture per enrollment
LBPH_RADIUS = 2                    # Samples a 5x5 ring — captures medium-scale texture
LBPH_NEIGHBORS = 16                # 65,536 histogram bins — highly discriminative
LBPH_GRID_X = 8                    # 8x8 spatial grid on 200x200 = 25 px/cell
LBPH_GRID_Y = 8
LBPH_THRESHOLD = 80.0              # Maximum distance to accept a match
REJECT_THRESHOLD = 80.0            # Distance above this = "Unknown"
MARGIN_THRESHOLD = 8.0             # Winner must beat runner-up by this much

# Preprocessing constants
GAMMA = 1.2
GAMMA_TABLE = np.array(
    [(i / 255.0) ** (1.0 / GAMMA) * 255 for i in range(256)], dtype=np.uint8
)
USM_ALPHA = 1.4   # unsharp mask: weight of original
USM_BETA = -0.4   # unsharp mask: weight of blurred (negative = subtract)
USM_SIGMA = 2.0   # unsharp mask: Gaussian sigma

# Quality gates
MIN_BLUR_VARIANCE = 60.0   # Laplacian variance — rejects blurry frames
MIN_BRIGHTNESS = 35.0
MAX_BRIGHTNESS = 220.0

# Paths
DATA_DIR = Path(__file__).parent / "lbph_reference_data"
SAMPLES_DIR = DATA_DIR / "samples"
MODEL_PATH = DATA_DIR / "lbph_model.yml"
LABELS_PATH = DATA_DIR / "labels.txt"

# ---------------------------------------------------------------------------
# Detectors (loaded once)
# ---------------------------------------------------------------------------
FACE_CASCADE = cv2.CascadeClassifier(
    str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
)
EYE_CASCADE = cv2.CascadeClassifier(
    str(Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml")
)
CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


# ---------------------------------------------------------------------------
# Preprocessing — matches EduScan's _processed_face pipeline exactly
# ---------------------------------------------------------------------------
def detect_face(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """Detect the largest frontal face using Haar cascade."""
    # Noise reduction: removes salt-and-pepper from cheap webcams
    denoised = cv2.medianBlur(gray, 3)

    # Downscale for faster detection
    scale = 0.5
    small = cv2.resize(denoised, None, fx=scale, fy=scale,
                       interpolation=cv2.INTER_AREA)
    small_eq = cv2.equalizeHist(small)

    faces = FACE_CASCADE.detectMultiScale(
        small_eq,
        scaleFactor=1.1,
        minNeighbors=6,
        minSize=(int(70 * scale), int(70 * scale)),
    )
    if len(faces) == 0:
        return None

    # Scale back to full resolution and return the largest face
    inv = 1.0 / scale
    boxes = [(int(x * inv), int(y * inv), int(w * inv), int(h * inv))
             for x, y, w, h in faces]
    return max(boxes, key=lambda b: b[2] * b[3])


def align_face(gray_crop: np.ndarray, eyes) -> np.ndarray:
    """Rotate face crop so both eyes are level — removes head-tilt variance."""
    if len(eyes) < 2:
        return gray_crop

    sorted_eyes = sorted(eyes, key=lambda e: e[2] * e[3], reverse=True)[:2]
    (ex1, ey1, ew1, eh1), (ex2, ey2, ew2, eh2) = sorted_eyes
    cx1, cy1 = ex1 + ew1 // 2, ey1 + eh1 // 2
    cx2, cy2 = ex2 + ew2 // 2, ey2 + eh2 // 2

    # Ensure left-eye is always first
    if cx1 > cx2:
        cx1, cy1, cx2, cy2 = cx2, cy2, cx1, cy1

    angle = float(np.degrees(np.arctan2(cy2 - cy1, cx2 - cx1)))
    center = ((cx1 + cx2) // 2, (cy1 + cy2) // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(gray_crop, M, (gray_crop.shape[1], gray_crop.shape[0]),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def preprocess_face(gray: np.ndarray, box: tuple[int, int, int, int],
                    strict: bool = True) -> np.ndarray | None:
    """Full preprocessing pipeline: crop -> quality check -> align -> enhance.

    Returns the 200x200 processed face or None if quality checks fail.
    """
    x, y, w, h = box

    # Add margin around the detection box (matches EduScan)
    margin_x, margin_y = int(w * 0.16), int(h * 0.20)
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(gray.shape[1], x + w + margin_x)
    y2 = min(gray.shape[0], y + h + margin_y)

    face_raw = cv2.resize(gray[y1:y2, x1:x2], FACE_SIZE,
                          interpolation=cv2.INTER_AREA)

    # --- Quality gates (measured on raw crop, before enhancement) ---
    blur = float(cv2.Laplacian(face_raw, cv2.CV_64F).var())
    brightness = float(face_raw.mean())

    if strict:
        if blur < MIN_BLUR_VARIANCE:
            return None  # too blurry
        if not MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS:
            return None  # lighting outside acceptable range

    # --- Eye detection on raw crop (consistent thresholds) ---
    upper_face = face_raw[:115, :]
    eyes = EYE_CASCADE.detectMultiScale(
        upper_face, scaleFactor=1.12, minNeighbors=5, minSize=(18, 18)
    )

    # --- Enhancement pipeline ---
    # Step 1: Eye alignment (removes head-tilt rotational variance)
    face_aligned = align_face(face_raw, eyes)
    # Step 2: Gamma lift (shadow recovery without blowing highlights)
    face_gamma = cv2.LUT(face_aligned, GAMMA_TABLE)
    # Step 3: CLAHE (local contrast normalization for uneven lighting)
    face_clahe = CLAHE.apply(face_gamma)
    # Step 4: Unsharp mask (sharpens texture edges that LBPH encodes)
    blur_kernel = cv2.GaussianBlur(face_clahe, (0, 0), USM_SIGMA)
    face_sharp = cv2.addWeighted(face_clahe, USM_ALPHA, blur_kernel, USM_BETA, 0)
    # Step 5: Min-max normalize (consistent [0, 255] intensity range)
    face = cv2.normalize(face_sharp, None, 0, 255, cv2.NORM_MINMAX)

    return face


# ---------------------------------------------------------------------------
# Label management (person_id <-> name mapping)
# ---------------------------------------------------------------------------
def load_labels() -> dict[int, str]:
    """Load {person_id: name} mapping from labels.txt."""
    if not LABELS_PATH.exists():
        return {}
    labels = {}
    for line in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        person_id, name = line.split(",", 1)
        labels[int(person_id)] = name
    return labels


def save_labels(labels: dict[int, str]) -> None:
    """Save {person_id: name} mapping to labels.txt."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LABELS_PATH.open("w", encoding="utf-8") as f:
        for person_id, name in sorted(labels.items()):
            f.write(f"{person_id},{name}\n")


def next_person_id(labels: dict[int, str]) -> int:
    return max(labels.keys(), default=0) + 1


# ---------------------------------------------------------------------------
# Enrollment: capture training images from webcam
# ---------------------------------------------------------------------------
POSE_GUIDE = [
    ("Look straight at the camera, relax your face", 10),
    ("Turn your head SLIGHTLY to the LEFT", 6),
    ("Turn your head SLIGHTLY to the RIGHT", 6),
    ("Tilt your chin UP just a little", 5),
    ("Tilt your chin DOWN just a little", 5),
    ("Give a slight SMILE", 5),
    ("Neutral face again -- look straight", 5),
    ("If you wear GLASSES, put them on/off now", 4),
    ("Look straight -- final captures", 4),
]


def enroll(name: str) -> None:
    """Capture SAMPLES_PER_PERSON training images with guided poses."""
    labels = load_labels()
    person_id = next_person_id(labels)
    person_dir = SAMPLES_DIR / f"person_{person_id}"
    person_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always get the freshest frame

    if not cap.isOpened():
        print("ERROR: Cannot open webcam")
        return

    print(f"\n=== Enrolling: {name} (ID: {person_id}) ===")
    print(f"Capturing {SAMPLES_PER_PERSON} quality frames. Follow the pose guides.\n")

    captured = 0
    rejected = 0
    pose_idx = 0
    frames_for_pose = 0
    current_instruction, target_for_pose = POSE_GUIDE[0]

    while captured < SAMPLES_PER_PERSON:
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        box = detect_face(gray)

        # --- UI overlay ---
        display = frame.copy()
        progress = f"Captured: {captured}/{SAMPLES_PER_PERSON}  |  Rejected: {rejected}"
        cv2.putText(display, progress, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(display, current_instruction, (10, 460),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)

        if box is not None:
            x, y, w, h = box
            face = preprocess_face(gray, box, strict=True)

            if face is not None:
                # Save the preprocessed face
                path = person_dir / f"{captured:04d}.png"
                cv2.imwrite(str(path), face)
                captured += 1
                frames_for_pose += 1

                # Green box for accepted
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(display, "OK", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Advance to next pose when target is met
                if frames_for_pose >= target_for_pose and pose_idx < len(POSE_GUIDE) - 1:
                    pose_idx += 1
                    frames_for_pose = 0
                    current_instruction, target_for_pose = POSE_GUIDE[pose_idx]
            else:
                rejected += 1
                # Red box for rejected (blurry or bad lighting)
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.putText(display, "LOW QUALITY", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            cv2.putText(display, "No face detected", (10, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        cv2.imshow("EduScan Enrollment", display)
        key = cv2.waitKey(100) & 0xFF
        if key == 27:  # ESC to abort
            print("Enrollment cancelled.")
            cap.release()
            cv2.destroyAllWindows()
            return

    cap.release()
    cv2.destroyAllWindows()

    labels[person_id] = name
    save_labels(labels)
    print(f"\nEnrolled '{name}' with {captured} quality frames (ID: {person_id})")
    print(f"   Rejected {rejected} frames for quality issues")
    print(f"   Samples saved to: {person_dir}")
    print(f"\n   Run 'python lbph_reference.py train' to rebuild the model.")


# ---------------------------------------------------------------------------
# Training: build LBPH model from all saved samples
# ---------------------------------------------------------------------------
def train_model() -> None:
    """Train the LBPH recognizer from all enrolled samples."""
    labels_map = load_labels()
    if not labels_map:
        print("ERROR: No enrolled people found. Run 'enroll' first.")
        return

    images: list[np.ndarray] = []
    labels: list[int] = []

    for person_id, name in labels_map.items():
        person_dir = SAMPLES_DIR / f"person_{person_id}"
        if not person_dir.exists():
            print(f"  WARNING: No samples directory for {name} (ID: {person_id})")
            continue

        count = 0
        for img_path in sorted(person_dir.glob("*.png")):
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                images.append(img)
                labels.append(person_id)
                count += 1

        print(f"  Loaded {count} samples for '{name}' (ID: {person_id})")

    if not images:
        print("ERROR: No sample images found.")
        return

    print(f"\nTraining LBPH with radius={LBPH_RADIUS}, neighbors={LBPH_NEIGHBORS}, "
          f"grid={LBPH_GRID_X}x{LBPH_GRID_Y}...")

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        LBPH_RADIUS, LBPH_NEIGHBORS, LBPH_GRID_X, LBPH_GRID_Y, LBPH_THRESHOLD
    )
    recognizer.train(images, np.array(labels, dtype=np.int32))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    recognizer.save(str(MODEL_PATH))

    person_count = len(set(labels))
    print(f"\nModel trained successfully:")
    print(f"   People: {person_count}")
    print(f"   Total samples: {len(images)}")
    print(f"   Model saved to: {MODEL_PATH}")
    print(f"\n   Run 'python lbph_reference.py recognize' to start recognition.")


# ---------------------------------------------------------------------------
# Recognition: real-time face recognition with confidence display
# ---------------------------------------------------------------------------
def predict_with_margin(recognizer, image: np.ndarray) -> tuple[int, float, float]:
    """Predict with margin check — same logic as EduScan's _predict_with_margin.

    Returns (label, best_distance, margin_to_next_different_label).
    """
    if hasattr(cv2.face, "StandardCollector_create"):
        try:
            collector = cv2.face.StandardCollector_create()
            recognizer.predict_collect(image, collector)
            raw = collector.getResults()
            if not raw:
                return -1, float("inf"), float("inf")
            best_label = int(raw[0][0])
            best_dist = float(raw[0][1])
            margin = float("inf")
            for lbl, dist in raw[1:]:
                if int(lbl) != best_label:
                    margin = float(dist) - best_dist
                    break
            return best_label, best_dist, margin
        except Exception:
            pass

    label, dist = recognizer.predict(image)
    return int(label), float(dist), float("inf")


def recognize() -> None:
    """Real-time recognition loop with confidence display."""
    labels_map = load_labels()
    if not labels_map:
        print("ERROR: No enrolled people. Run 'enroll' and 'train' first.")
        return

    if not MODEL_PATH.exists():
        print("ERROR: No trained model. Run 'train' first.")
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(MODEL_PATH))
    print("Model loaded successfully.")

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("ERROR: Cannot open webcam")
        return

    print("\n=== EduScan LBPH Recognition ===")
    print(f"Rejection threshold: distance > {REJECT_THRESHOLD}")
    print(f"Margin threshold: {MARGIN_THRESHOLD}")
    print("Press ESC to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        box = detect_face(gray)
        display = frame.copy()

        if box is not None:
            x, y, w, h = box
            face = preprocess_face(gray, box, strict=False)

            if face is not None:
                label, distance, margin = predict_with_margin(recognizer, face)

                if label != -1 and distance <= REJECT_THRESHOLD:
                    if margin < MARGIN_THRESHOLD:
                        # Ambiguous match — two people are too close in distance
                        color = (0, 165, 255)  # orange
                        name_text = "AMBIGUOUS"
                        detail = f"d={distance:.1f} margin={margin:.1f}"
                    else:
                        # Confident match
                        name = labels_map.get(label, f"ID-{label}")
                        confidence_pct = max(0, 100 - distance)

                        # Color: green for strong, yellow for weak
                        if distance < 50:
                            color = (0, 255, 0)   # strong match
                        else:
                            color = (0, 255, 255)  # weaker but accepted

                        name_text = name
                        detail = f"d={distance:.1f} ({confidence_pct:.0f}%)"
                else:
                    # Unknown / rejected
                    color = (0, 0, 255)  # red
                    name_text = "UNKNOWN"
                    detail = f"d={distance:.1f} > {REJECT_THRESHOLD}"

                cv2.rectangle(display, (x, y), (x + w, y + h), color, 2)
                cv2.putText(display, name_text, (x, y - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.putText(display, detail, (x, y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                # Show the preprocessed face in corner for debugging
                face_rgb = cv2.cvtColor(face, cv2.COLOR_GRAY2BGR)
                face_small = cv2.resize(face_rgb, (100, 100))
                display[10:110, 530:630] = face_small
            else:
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 0, 255), 1)

        cv2.putText(display, "ESC to quit", (10, 470),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.imshow("EduScan LBPH Recognition", display)

        if (cv2.waitKey(1) & 0xFF) == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Recognition stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="EduScan LBPH Reference -- enroll, train, recognize"
    )
    sub = parser.add_subparsers(dest="command")

    enroll_parser = sub.add_parser("enroll", help="Capture training images for a person")
    enroll_parser.add_argument("name", help="Person's full name")

    sub.add_parser("train", help="Train the LBPH model from all enrolled samples")
    sub.add_parser("recognize", help="Run real-time recognition")

    args = parser.parse_args()

    if args.command == "enroll":
        enroll(args.name)
    elif args.command == "train":
        train_model()
    elif args.command == "recognize":
        recognize()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
