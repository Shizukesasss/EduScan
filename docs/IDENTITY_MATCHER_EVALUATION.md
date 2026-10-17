The user confirmed that both displayed saved enrollment labels are correct. Fresh Markie camera testing nevertheless ranked Bryani at LBPH distance 44.01 and Markie at 70.01 (cutoff 65). A cutoff adjustment cannot correct that ranking.

An isolated SFace feasibility evaluation was run using existing encrypted samples, decoded only in memory under a read-only database transaction. The model and Apache 2.0 license are in work/sface-evaluation; nothing imports or activates them in the app. Installed OpenCV 4.12.0 already supports FaceRecognizerSF and FaceDetectorYN.

Model: official OpenCV face_recognition_sface_2021dec.onnx, 38,696,353 bytes, SHA-256 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79. Source: https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface

Method: Detect landmarks on each existing grayscale sample converted to BGR, use FaceRecognizerSF.alignCrop and feature, normalize features, and compare cosine similarity. For every stored sample, exclude that exact sample and choose the nearest remaining sample across the two enrollments. This is a feasibility check on correlated enrollment samples, not an independent accuracy benchmark or calibration of a deployment threshold.

Results:
- Markie: 20/20 nearest matches to correct stored identity. Nearest same-person cosine similarities min/median/max 0.930/0.959/0.969; nearest other-person 0.216/0.260/0.296.
- Bryani: 16/16 nearest matches to correct stored identity. Nearest same-person similarities 0.865/0.917/0.942; nearest other-person 0.172/0.262/0.296.

No live images, feature vectors, school database rows, enrollments, model registrations, attendance, SMS, or recognition reviews were saved or changed. Only the public model and license were downloaded. The existing live LBPH approach and authorized anti-spoof rollback remain unchanged.

Proposed next step, pending user approval: Integrate SFace into read-only Camera Test first, preserving enrollment datasets and live attendance behavior. Then validate fresh Markie, Bryani, both together, and unknown-person negatives before discussing live activation. SFace verifies identity; it does not restore photo/video protection. Reference implementation and thresholds: https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html
