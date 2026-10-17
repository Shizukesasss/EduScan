export function buildEnrollmentFeedback(error, isReplacement = false) {
  const reasons = [...new Set((Array.isArray(error.details?.rejected) ? error.details.rejected : [])
    .map(reason => reason.replace(/^Frame \d+:\s*/, '')))];
  const scores = error.details?.presentation;
  if (scores && Number.isFinite(scores.minimum_live_score) && Number.isFinite(scores.maximum_live_score)) {
    reasons.unshift(`Live-face score range: ${scores.minimum_live_score.toFixed(3)}–${scores.maximum_live_score.toFixed(3)}; required: ${scores.required_live_score}. ${scores.failed_frames} of ${scores.frames_checked} checked frames failed.`);
  }
  const messages = {
    presentation_check_failed: 'We couldn’t verify a live face clearly. Use brighter, even lighting, face the camera directly, and blink once during capture. Avoid glare and bright light behind you.',
    liveness_check_failed: 'We didn’t catch a complete blink. Look at the camera with your eyes open, blink once, then open them again during capture.',
    human_face_required: 'We couldn’t get a clear view of your face. Face the camera, improve the lighting, and keep your eyes, nose, and mouth visible.',
  };
  const duplicate = ['duplicate_face', 'possible_duplicate_face'].includes(error.code);
  const multipleFaces = !messages[error.code] && [error.message, ...reasons].some(reason => /more than one|only one human face/i.test(reason));
  return {
    title: duplicate ? 'Face may already be enrolled' : 'Enrollment needs your attention',
    message: messages[error.code] || (multipleFaces
      ? 'We couldn’t confirm that only one person was in view. Keep other people, face photos, and reflections out of the camera view, then capture again.'
      : error.message),
    reasons,
    note: isReplacement ? 'Your existing face enrollment is unchanged.' : 'No face samples were saved by this attempt.',
  };
}

export function cameraTestMatchMessage(match) {
  const code = match.presentation_verified === false ? 'presentation_check_failed'
    : match.recognized && !match.liveness_verified ? 'liveness_check_failed' : undefined;
  return code ? buildEnrollmentFeedback({ code, message: match.message }).message : match.message;
}


export function cameraIdentityScore(match) {
  if (Number.isFinite(match.identity_similarity)) return `SFace similarity ${match.identity_similarity.toFixed(3)}`;
  if (Number.isFinite(match.distance)) return `distance ${match.distance.toFixed(1)}`;
  return 'Identity score unavailable';
}
