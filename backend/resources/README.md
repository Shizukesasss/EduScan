# Local camera models

`face_detection_yunet_2023mar.onnx` is the OpenCV Zoo YuNet face detector. EduScan's OpenCV 4.12 runtime uses this version to check human facial landmarks locally before enrollment. LBPH remains the identity recognizer.

- Source: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- Model download: https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
- SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`
- Size: 232589 bytes
- License: MIT; original attribution and terms are in `YUNET-LICENSE.txt`.

Keep this bundled file with the application. Human-face verification fails closed if it is missing or fails its integrity check. No camera frames are sent to OpenCV or another online service. The detector and geometric landmark checks reduce animal/object false positives; they are not a perfect species classifier. Validate with representative authorized human captures and animal/object negatives before deployment.

## Photo/video presentation check

`anti-spoof-mn3.onnx` is the MobileNetV3 model trained on CelebA-Spoof and distributed by Intel's Open Model Zoo. It runs locally through the installed OpenCV DNN runtime; no new Python dependency is required. It checks every verified face crop on all attendance recognition routes, independently of LBPH and blinking. Enrollment remains supervised and uses the existing enrollment checks.

- [Official model description and input/output contract](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/public/anti-spoof-mn3/README.md)
- [Official download manifest, size, and checksum](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/public/anti-spoof-mn3/model.yml)
- Download: https://storage.openvinotoolkit.org/repositories/open_model_zoo/public/2022.1/anti-spoof-mn3/anti-spoof-mn3.onnx
- Size: 12,270,179 bytes.
- SHA-256: `c4c99af04603b62d7e44f6f4daeb33e0daeccc696008c0b1d62f6f5cebbb3262`.
- Upstream SHA-384, checked at download: `6de4534964b723397b3e8c995cadcf43bc007cc2f9930b95ae25f76adccece5d1d4d058d0b15117b9e4a9f758424f92a`.
- Model license: MIT; see `ANTI-SPOOF-LICENSE.txt`.

The original ONNX takes a tight face crop resized to 128×128 using cubic interpolation, converted from BGR to RGB and normalized per channel with mean `[151.2405,119.5950,107.8395]` and scale `[63.0105,56.4570,55.0035]`. Output is `[live, spoof]`; no second softmax is applied. Acceptance requires a live score of at least 0.6, matching the [upstream demo's 0.4 spoof cutoff](https://github.com/kprokofi/light-weight-face-anti-spoofing/blob/master/demo/demo.py). This score is not a calibrated probability for school cameras.

Missing, corrupt, unreadable, or invalid model output blocks camera attendance. Staff assistance remains available. Any failed presentation score for a recognized identity invalidates its entire capture burst, including an earlier completed blink; other identities are evaluated separately. Disabling the optional blink challenge does not disable the presentation check.

This classifier reduces photo/screen replay risk; it cannot guarantee detection of every attack. Validate real students and separate print/display attacks under school lighting. A stronger deployment may require a validated presentation-attack solution with trusted depth/IR hardware. Keep the assisted option for people who cannot pass camera checks.
