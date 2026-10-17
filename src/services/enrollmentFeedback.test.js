import test from 'node:test';
import assert from 'node:assert/strict';
import { buildEnrollmentFeedback, cameraTestMatchMessage, cameraIdentityScore } from './enrollmentFeedback.js';

test('replay warning gives clear guidance and keeps detailed reasons separate', () => {
  const feedback = buildEnrollmentFeedback({ code: 'presentation_check_failed', message: 'Raw technical failure',
    details: { rejected: ['Frame 1: photo/video protection did not pass', 'Frame 2: photo/video protection did not pass'] } });
  assert.match(feedback.message, /lighting/);
  assert.doesNotMatch(feedback.message, /Raw technical|Frame checks/);
  assert.equal(feedback.reasons.length, 1);
});

test('multiple-face warning avoids asserting that another person was definitely present', () => {
  const feedback = buildEnrollmentFeedback({ message: 'Only 0 quality frames were accepted',
    details: { rejected: ['Frame 1: More than one face was detected'] } });
  assert.match(feedback.message, /couldn’t confirm/);
});

test('duplicate warnings preserve the matching identity and existing-enrollment notice', () => {
  const feedback = buildEnrollmentFeedback({ code: 'duplicate_face', message: 'Already enrolled as Markie.' }, true);
  assert.match(feedback.message, /Markie/);
  assert.match(feedback.note, /unchanged/);
});

test('gate camera tests reuse enrollment replay and blink guidance', () => {
  for (const [match, code] of [
    [{ presentation_verified: false, recognized: true, liveness_verified: true }, 'presentation_check_failed'],
    [{ presentation_verified: true, recognized: true, liveness_verified: false }, 'liveness_check_failed'],
  ]) assert.equal(cameraTestMatchMessage(match), buildEnrollmentFeedback({ code }).message);
});

test('successful recognition and unknown identities keep their own explanations', () => {
  for (const match of [
    { presentation_verified: true, recognized: true, liveness_verified: true, message: 'Verified' },
    { presentation_verified: true, recognized: false, liveness_verified: false, message: 'No matching identity' },
  ]) assert.equal(cameraTestMatchMessage(match), match.message);
});

test('test score diagnostics stay in capture details rather than the warning message', () => {
  const feedback = buildEnrollmentFeedback({ code: 'presentation_check_failed', details: {
    presentation: { minimum_live_score: .12, maximum_live_score: .99,
      required_live_score: .6, failed_frames: 1, frames_checked: 20 },
  } });
  assert.match(feedback.reasons[0], /0.120–0.990/);
  assert.match(feedback.reasons[0], /1 of 20/);
  assert.doesNotMatch(feedback.message, /0.120|1 of 20/);
});


test('restored flow does not claim absent photo/video verification failed', () => {
  assert.equal(cameraTestMatchMessage({ presentation_verified: null, recognized: true,
    liveness_verified: true, message: 'Identity verified' }), 'Identity verified');
});


test('SFace and LBPH scores use distinct labels and missing scores render safely', () => {
  assert.equal(cameraIdentityScore({ identity_similarity: .8, distance: null }), 'SFace similarity 0.800');
  assert.equal(cameraIdentityScore({ distance: 44.01 }), 'distance 44.0');
  assert.equal(cameraIdentityScore({ identity_similarity: null, distance: null }), 'Identity score unavailable');
});
