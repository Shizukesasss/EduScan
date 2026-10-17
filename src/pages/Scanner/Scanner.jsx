import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Camera, CheckCircle2, Clock3, KeyRound, LayoutDashboard, LogOut, Maximize2, MessageSquareText, Minimize2, RefreshCw, ScanFace, UserPlus } from 'lucide-react';
import { api, auth, captureVideoFrame, displayTime, localDate, enrollmentCapture } from '../../api/client';
import StudentRegistrationModal from '../../components/Scanner/StudentRegistrationModal';
import { buildEnrollmentFeedback, cameraTestMatchMessage, cameraIdentityScore } from '../../services/enrollmentFeedback';

export default function Scanner({ testMode = false }) {
  const [previewOnly] = useState(() => !testMode && new URLSearchParams(window.location.search).get('preview') === '1');
  const videoRef = useRef(null);
  const cameraFrameRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const busyRef = useRef(false);
  const scanningRef = useRef(false);
  const scanGenerationRef = useRef(0);
  const pendingScanRef = useRef(null);
  const logBusyRef = useRef(false);
  const feedbackTimerRef = useRef(null);
  const stationIdRef = useRef(null);
  useEffect(() => {
    if (testMode || previewOnly) return;
    stationIdRef.current = localStorage.getItem('eduscan.stationId') || crypto.randomUUID();
    localStorage.setItem('eduscan.stationId', stationIdRef.current);
  }, [testMode, previewOnly]);
  const [cameraOn, setCameraOn] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [events, setEvents] = useState([]);
  const [outboxCount, setOutboxCount] = useState(0);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [cameraFullscreen, setCameraFullscreen] = useState(false);
  const [stationHealth, setStationHealth] = useState({ api: false, database: false, gateway_enabled: false, gateway_reachable: false, recognition_model: false });
  const [backendReachable, setBackendReachable] = useState(true);
  const [testCase, setTestCase] = useState('Live person');
  const [testPurpose, setTestPurpose] = useState('sface');
  const [testRuns, setTestRuns] = useState([]);

  const refreshLog = useCallback(() => {
    if (testMode || previewOnly) return;
    if (logBusyRef.current) return;
    logBusyRef.current = true;
    return Promise.allSettled([
        api.get(`/gate/recent?date=${localDate()}`),
        auth.role() === 'admin' ? api.get('/sms/outbox') : Promise.resolve(null),
      ]).then(([recent, outbox]) => {
      if (recent.status === 'fulfilled') setEvents(recent.value);
      if (outbox.status === 'fulfilled' && outbox.value) setOutboxCount(outbox.value.length);
    }).catch((err) => setFeedback({ ok: false, message: err.message }))
      .finally(() => { logBusyRef.current = false; });
  }, [testMode, previewOnly]);

  useEffect(() => { refreshLog(); }, [refreshLog]);
  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const result = await api.get('/station/health');
        if (mounted) {
          setStationHealth(result); setBackendReachable(true);
          if (result.recognition_model === false && scanningRef.current && !(testMode && testPurpose !== 'recognition')) {
            clearInterval(timerRef.current); scanningRef.current = false; scanGenerationRef.current += 1; setScanning(false);
            setFeedback({ ok: false, message: result.recognition_message || 'Restore or train the face model before recognition.' });
          }
        }
      }
      catch { if (mounted) setBackendReachable(false); }
    };
    check(); const timer = window.setInterval(check, 10000);
    return () => { mounted = false; clearInterval(timer); };
  }, [testMode, testPurpose]);
  useEffect(() => () => {
    clearInterval(timerRef.current);
    clearTimeout(feedbackTimerRef.current);
    scanningRef.current = false;
    scanGenerationRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);
  useEffect(() => {
    const updateFullscreenState = () => setCameraFullscreen(document.fullscreenElement === cameraFrameRef.current);
    document.addEventListener('fullscreenchange', updateFullscreenState);
    return () => document.removeEventListener('fullscreenchange', updateFullscreenState);
  }, []);

  const startCamera = async () => {
    pauseRecognition();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraOn(false);
    const generation = scanGenerationRef.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 960 }, height: { ideal: 720 } }, audio: false });
      if (generation !== scanGenerationRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      stream.getVideoTracks().forEach((track) => track.addEventListener('ended', () => {
        if (streamRef.current !== stream) return;
        pauseRecognition();
        setCameraOn(false);
        setFeedback({ ok: false, message: 'The camera connection stopped. Click Enable camera to reconnect, then check that your live preview is visible before testing.' });
      }, { once: true }));
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCameraOn(true);
      setFeedback({ ok: true, message: testMode ? 'Test camera ready. Choose a test and hold the photo, video, or live faces in view. No attendance or SMS will be created.' : 'Camera is ready. Start recognition when the gate lane is clear.' });
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraOn(false);
      setFeedback({ ok: false, message: `Camera could not start: ${err.message}` });
    }
  };

  const scanOnce = useCallback(async () => {
    if (!scanningRef.current || busyRef.current || !videoRef.current?.videoWidth) return;
    busyRef.current = true;
    const generation = scanGenerationRef.current;
    try {
      const form = new FormData();
      let lastFrame;
      const startedAt = videoRef.current.currentTime;
      // Capture enough closely spaced observations to catch a natural blink,
      // then perform one request instead of a cloud round trip per frame.
      const enrollmentTest = testMode && testPurpose === 'enrollment';
      const sfaceTest = testMode && testPurpose === 'sface';
      const highQualityTest = testMode && testPurpose !== 'recognition';
      const frameCount = enrollmentTest ? enrollmentCapture.frames : 40;
      for (let index = 0; index < frameCount; index++) {
        if (!scanningRef.current || generation !== scanGenerationRef.current) return;
        const blob = await captureVideoFrame(videoRef.current, sfaceTest ? 0.9 : highQualityTest ? enrollmentCapture.quality : 0.9, enrollmentCapture.maxDimension);
        lastFrame = blob;
        form.append('frames', blob, `gate-${index}.jpg`);
        if (index < frameCount - 1) await new Promise(resolve => window.setTimeout(resolve, enrollmentTest ? enrollmentCapture.interval : 100));
      }
      if (videoRef.current.currentTime <= startedAt || videoRef.current.paused) {
        throw new Error('The camera preview is not updating. Reconnect the camera before trying recognition again.');
      }
      // Older running servers still accept their original single-frame field
      // until the updated API is restarted.
      if (!testMode && !previewOnly) {
        form.append('frame', lastFrame, 'gate.jpg');
        form.append('station_id', stationIdRef.current);
      }
      if (!scanningRef.current || generation !== scanGenerationRef.current) return;
      if (testMode) form.append('mode', testPurpose);
      const request = api.post(previewOnly ? '/biometrics/recognize-preview' : testMode ? '/biometrics/test' : '/biometrics/recognize-many', form, { signal: AbortSignal.timeout(30000) });
      pendingScanRef.current = request;
      const batch = await request;
      if (!scanningRef.current || generation !== scanGenerationRef.current) return;
      setBackendReachable(true);
      if (previewOnly) {
        if (batch.preview_only !== true || batch.attendance_enabled !== false || !Array.isArray(batch.results)
            || batch.results.some(item => item.attendance_event?.recorded !== false)) {
          clearInterval(timerRef.current); scanningRef.current = false; setScanning(false);
          setFeedback({ ok: false, message: 'Preview safety could not be confirmed. Recognition stopped; reload the updated server before retrying.' });
          return;
        }
        const matched = batch.results.filter(item => item.recognized).length;
        const verified = batch.results.filter(item => item.camera_checks_passed).length;
        const message = `Preview only: ${batch.face_count} face(s) detected, ${matched} matched, ${verified} passed identity and blink checks. No attendance, SMS, review changes, or camera frames saved.`;
        const results = batch.results.map(item => ({ ...item, message: cameraTestMatchMessage(item) }));
        setFeedback({ ok: verified > 0, message, batch: results });
        setTestRuns(previous => [{ id: crypto.randomUUID(), name: 'Recognition preview', message,
          details: results.map(item => `${item.person?.full_name || 'Unknown person'}: ${item.message} · ${cameraIdentityScore(item)}`) }, ...previous].slice(0, 12));
        return;
      }
      if (testMode) {
        const frameRate = streamRef.current?.getVideoTracks()[0]?.getSettings().frameRate;
        const cameraDetails = `Camera capture: ${videoRef.current.videoWidth} × ${videoRef.current.videoHeight}; ${frameRate ?? 'unknown'} frames per second.`;
        if (batch.test_mode !== true || batch.attendance_enabled !== false || batch.results.some(item => item.attendance_event?.recorded)) {
          throw new Error('Test safety response was invalid. Stop testing and ask the administrator to check the server.');
        }
        if (enrollmentTest) {
          if (!batch.enrollment) throw new Error('Enrollment test is unavailable. Restart the updated EduScan API.');
          const passed = batch.enrollment.can_enroll;
          const replayAccepted = false;
          const warning = passed ? null : buildEnrollmentFeedback({ code: batch.enrollment.code,
            message: batch.enrollment.message, details: batch.enrollment });
          const message = `${testCase} · Enrollment: ${warning?.message || batch.enrollment.message} No attendance, SMS, reviews, enrollment, or camera frames were saved.`;
          const reasons = [cameraDetails, ...(warning?.reasons || buildEnrollmentFeedback({ details: batch.enrollment }).reasons)];
          setTestRuns(previous => [{ id: crypto.randomUUID(), name: `Enrollment · ${testCase}`, message, replayAccepted, details: reasons }, ...previous].slice(0, 12));
          setFeedback({ ok: passed && !replayAccepted, message, reasons });
          return;
        }
        const passed = batch.results.filter(item => item.camera_checks_passed).length;
        const recognized = batch.results.filter(item => item.recognized).length;
        const replayAccepted = false;
        const message = `${batch.matcher === 'SFace' ? 'SFace test · ' : ''}${testCase}: up to ${batch.max_faces_in_frame} clear face(s) seen together · ${recognized} identity match(es)${batch.result_scope === 'capture' ? ' during this capture' : ' in the latest frame'}${batch.matcher === 'SFace' ? ` · up to ${batch.max_identities_in_frame} identities matched together` : ''} · ${passed} passed recognition and configured blink checks. No attendance or SMS was created.`;
        const reasons = [cameraDetails, 'Photo/video protection is disabled in the restored recognition flow.',
          ...(batch.identity_comparisons || []).map(comparison =>
            `Face ${comparison.face} identity ${batch.matcher === 'SFace' ? 'similarities (higher is closer' : 'distances (lower is closer'}; cutoff ${comparison.threshold}): ${comparison.candidates.map(candidate => `${candidate.name}: ${candidate.similarity ?? candidate.distance}`).join('; ')}`)];
        setTestRuns(previous => [{ id: crypto.randomUUID(), name: testCase, message, replayAccepted, details: reasons }, ...previous].slice(0, 12));
        setFeedback({ ok: passed > 0 && !replayAccepted,
          reasons,
          batch: batch.results.map(item => ({ ...item, message: cameraTestMatchMessage(item) })),
          message: replayAccepted ? `REPLAY PASSED — protection needs review. ${message}` : message });
        return;
      }
      const recorded = batch.results.filter((item) => item.attendance_event?.recorded);
      const recognized = batch.results.filter((item) => item.recognized);
      const held = batch.results.filter(item => item.attendance_event?.presence_hold);
      const blocked = batch.results.filter(item => item.presentation_verified === false);
      setFeedback({ ok: recorded.length > 0 || held.length > 0, batch: batch.results,
        message: (held.length > 0 && recorded.length === 0 ? 'Attendance is already saved for this visit. Leave the camera view before scanning again.'
          : `${batch.face_count} face(s) detected · ${recognized.length} recognized · ${recorded.length} attendance event(s) recorded.`)
          + (blocked.length ? ` ${blocked.length} capture(s) did not pass photo/video protection; use a live face or ask staff for assistance.` : '') });
      if (recorded.length) {
        setEvents(previous => [...recorded.map(item => ({ id: item.attendance_event.id, name: item.person.full_name, role: item.person.role,
          direction: item.attendance_event.direction, status: item.attendance_event.status, time: item.attendance_event.time })), ...previous].slice(0, 30));
        void refreshLog();
        clearTimeout(feedbackTimerRef.current);
        feedbackTimerRef.current = window.setTimeout(() => setFeedback(null), 7000);
      }
    } catch (err) {
      if (!scanningRef.current || generation !== scanGenerationRef.current) return;
      if (err.message.includes('backend is not reachable')) setBackendReachable(false);
      if (['model_not_trained', 'model_file_missing', 'model_key_mismatch', 'model_integrity_failed', 'model_unreadable', 'presentation_verifier_unavailable', 'identity_verifier_unavailable'].includes(err.code) || err.message.includes('No trained LBPH model is available')) {
        clearInterval(timerRef.current); scanningRef.current = false; scanGenerationRef.current += 1; setScanning(false);
      }
      const warning = testMode ? buildEnrollmentFeedback(err) : null;
      setFeedback({ ok: false, message: warning?.message || err.message, reasons: warning?.reasons });
      if (testMode) setTestRuns(previous => [{ id: crypto.randomUUID(), name: testCase, message: `No complete result: ${warning.message}`, replayAccepted: false }, ...previous].slice(0, 12));
    } finally {
      pendingScanRef.current = null; busyRef.current = false;
      if (testMode && generation === scanGenerationRef.current) { scanningRef.current = false; setScanning(false); }
    }
  }, [refreshLog, testMode, testCase, testPurpose, previewOnly]);

  const pauseRecognition = () => {
    clearInterval(timerRef.current);
    clearTimeout(feedbackTimerRef.current);
    scanningRef.current = false;
    scanGenerationRef.current += 1;
    setScanning(false);
    setFeedback({ ok: true, message: 'Recognition paused. No current identity is being shown.' });
  };

  const openEnrollment = async () => {
    pauseRecognition();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    setCameraOn(false);
    setFeedback({ ok: true, message: 'Recognition is paused for enrollment. Enable the gate camera and start recognition separately when attendance should be recorded.' });
    // Finish a gate request sent before enrollment, then keep recognition paused.
    try { await pendingScanRef.current; } catch { /* the scan error is handled separately */ }
    setRegistrationOpen(true);
  };

  const toggleScanning = () => {
    if (registrationOpen || !cameraOn) return;
    if (scanning) {
      pauseRecognition(); return;
    }
    if (testMode && busyRef.current) {
      setFeedback({ ok: false, message: 'The previous test is finishing. Wait for it to finish, then run the next test.' });
      return;
    }
    if (stationHealth?.recognition_model === false && !(testMode && testPurpose !== 'recognition')) {
      setFeedback({ ok: false, message: stationHealth.recognition_message || 'Restore or train the face model before recognition.' });
      return;
    }
    scanningRef.current = true;
    setScanning(true);
    setFeedback({ ok: true, message: 'Checking the current camera view…' });
    scanOnce();
    if (!testMode) timerRef.current = window.setInterval(scanOnce, 200);
  };

  const restartRecognition = () => {
    if (registrationOpen || !cameraOn) return;
    if (stationHealth?.recognition_model === false) {
      setFeedback({ ok: false, message: stationHealth.recognition_message || 'Restore or train the face model before recognition.' });
      return;
    }
    pauseRecognition();
    setFeedback({ ok: true, message: 'Recognition loop restarted in a controlled state. The camera stream remains active.' });
    scanningRef.current = true; setScanning(true); scanOnce(); timerRef.current = window.setInterval(scanOnce, 200);
  };

  const toggleCameraFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (cameraFrameRef.current?.requestFullscreen) await cameraFrameRef.current.requestFullscreen();
      else setFeedback({ ok: false, message: 'Full-screen camera is not supported by this browser. The enlarged scanner view is still available.' });
    } catch (err) {
      setFeedback({ ok: false, message: `Full-screen camera could not start: ${err.message}` });
    }
  };

  const logout = () => { auth.clear(); window.location.href = '/login'; };

  return (
    <div className="scanner-shell">
      <header className="scanner-header">
        <div className="brand-lockup"><img src="/logo.png" alt="San Jose National High School logo" /><div><h2>{testMode ? 'EduScan Camera Test' : 'EduScan Gate Station'}</h2><span>{previewOnly ? 'Preview only · nothing is saved' : testMode ? 'Test only · attendance and SMS disabled' : 'San Jose National High School · local biometric station'}</span></div></div>
        <div className="action-row">
          {auth.role() === 'admin' && (
            <>
              <button className="btn-secondary" onClick={() => window.location.href = '/dashboard'}><LayoutDashboard size={16} /> Dashboard</button>
              {!testMode && <button className="btn-secondary" disabled={previewOnly} title={previewOnly ? 'Open the normal scanner to enroll a person' : undefined} onClick={openEnrollment}><UserPlus size={16} /> Enroll person</button>}
            </>
          )}
          <button className="icon-btn" title="Account security" aria-label="Account security" onClick={() => { window.location.href = '/account/security'; }}><KeyRound size={18} /><span className="control-label">Account security</span></button>
          {previewOnly && <a className="btn-secondary" href="/scanner">Open normal scanner</a>}
          <div className="scanner-state"><span className={`status-dot ${scanning ? '' : 'warning-dot'}`} /> {scanning ? previewOnly ? 'PREVIEW ACTIVE' : testMode ? 'TEST CAPTURE ACTIVE' : 'RECOGNITION ACTIVE' : cameraOn ? 'CAMERA READY' : 'CAMERA OFF'}</div>
          <button className="icon-btn" onClick={logout} title="Sign out"><LogOut size={18} /><span className="control-label">Sign out</span></button>
        </div>
      </header>

      <main className="scanner-main">
        <section className="scanner-stage">
          {previewOnly && <div className="notice notice-blue" role="status"><div><strong>Preview only</strong><p>This uses the main scanner's identity and configured blink checks. Keep both people visible and blink naturally. No attendance, SMS, review changes, enrollment, or camera frames are saved. Photo/video protection remains disabled in the restored flow.</p></div></div>}
          {testMode && <div className="notice notice-blue" role="status"><div><strong>TEST MODE — no attendance, SMS, review changes, or saved camera frames</strong><p>SFace identity matching is shared with enrollment and the gate scanner. This page only tests it; attendance remains disabled. Run each test separately. Keep your own face outside the view during photo/video tests. Photo/video protection has been removed from the restored flow. These tests do not verify resistance to photos or videos. For gate tests, blink naturally if required. Enroll Person checks use the same capture settings, quality, human-face, and shared identity checks as real enrollment. An already-enrolled face should be blocked as a duplicate. Enrollment requires one person; group tests can use SFace identity checks or Gate recognition checks.</p><label><span className="field-label">Camera checks</span><select className="input-field" value={testPurpose} disabled={scanning} onChange={event => { setTestPurpose(event.target.value); if (event.target.value === 'enrollment' && testCase.endsWith(' people')) setTestCase('Live person'); setFeedback(null); }}><option value="sface">SFace identity checks — test only</option><option value="enrollment">Enroll Person checks</option><option value="recognition">Gate recognition checks</option></select></label><label><span className="field-label">Test to run</span><select className="input-field" value={testCase} disabled={scanning} onChange={event => { setTestCase(event.target.value); if (event.target.value.endsWith(' people') && testPurpose === 'enrollment') setTestPurpose('sface'); setFeedback(null); }}><option>Live person</option><option>Photo</option><option>Video</option><option>2 people</option><option>3 people</option><option>5 people</option><option>10 people</option></select></label></div></div>}
          {scanning && !backendReachable && <div className="notice notice-danger scanner-backend-warning"><AlertTriangle size={22} /><div><strong>Attendance backend unavailable.</strong> Recognition is paused from recording attendance or SMS notices. Keep people at the gate and use the documented manual attendance fallback until the API is restored.</div></div>}
          <div className="station-health-strip"><span className={`tag ${backendReachable && stationHealth.database ? 'tag-success' : 'tag-danger'}`}>API / database: {backendReachable && stationHealth.database ? 'ready' : 'unavailable'}</span><span className={`tag ${cameraOn ? 'tag-success' : 'tag-gray'}`}>Camera: {cameraOn ? 'ready' : 'off'}</span><span className={`tag ${stationHealth.gateway_enabled && stationHealth.gateway_reachable ? 'tag-success' : 'tag-warning'}`}>SMS: {previewOnly ? 'disabled in preview' : stationHealth.gateway_enabled ? stationHealth.gateway_reachable ? 'reachable' : 'unreachable' : 'disabled'}</span><span className={`tag ${stationHealth.recognition_model ? 'tag-success' : 'tag-warning'}`}>LBPH: {stationHealth.recognition_model ? 'ready' : 'model missing'}</span></div>
          <div className="camera-placeholder live-camera" ref={cameraFrameRef}>
            <video ref={videoRef} playsInline muted aria-label="Gate camera preview" />
            {!cameraOn && <div className="camera-frame"><Camera size={78} /><h1>Gate camera</h1><p>Camera frames are processed by the local LBPH server and are not uploaded to a cloud service.</p></div>}
            {scanning && <div className="multi-face-guide"><span>Multi-face scan area · keep every person inside the frame and facing the camera</span></div>}
            <button className="camera-fullscreen-toggle" onClick={toggleCameraFullscreen} title={cameraFullscreen ? 'Exit full-screen camera' : 'Open full-screen camera'}>
              {cameraFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              <span>{cameraFullscreen ? 'Exit full screen' : 'Full-screen camera'}</span>
            </button>
          </div>

          <div className="scanner-control-panel">
            <div><p className="eyebrow">{previewOnly ? 'Preview only' : testMode ? 'Read-only camera checks' : 'Live local processing'}</p><h2>{testMode ? 'Photo, video, and group tests' : cameraOn ? 'Multi-face LBPH recognition station' : 'Start the secured gate camera'}</h2><p>{previewOnly ? 'Recognition repeats in four-second captures using the main scanner flow. Each person must pass identity and configured blink checks. Nothing is saved. Pause recognition when finished.' : testMode ? 'Each test captures four seconds, runs the same camera checks, then stops. Even if every check passes, this page cannot save attendance. Results stay on this page until you reload or leave.' : 'Up to 10 people can face the camera together. Each person must pass the configured recognition and blink checks separately. Photo/video protection is disabled in this restored flow. Show your live face directly, without a photo or screen. Attendance is recorded once per visit; leave the camera view before returning for the next time-in or time-out.'}</p></div>
            <div className="scanner-control-actions">
              {!cameraOn ? <button className="btn-primary" onClick={startCamera}><Camera size={18} /> Enable camera</button>
                : <button className={scanning ? 'btn-secondary' : 'btn-primary'} disabled={!scanning && (!backendReachable || (!(testMode && testPurpose !== 'recognition') && stationHealth?.recognition_model === false))} onClick={toggleScanning}><ScanFace size={18} /> {scanning ? testMode ? 'Cancel test' : 'Pause recognition' : testMode ? 'Run 4-second test' : 'Start recognition'}</button>}
              {cameraOn && !testMode && <button className="btn-secondary" disabled={!backendReachable || stationHealth?.recognition_model === false} onClick={restartRecognition}><RefreshCw size={18} /> Restart recognition</button>}
              {cameraOn && testMode && <button className="btn-secondary" disabled={scanning} onClick={startCamera}><RefreshCw size={18} /> Reconnect camera</button>}
              <button className="btn-secondary" onClick={toggleCameraFullscreen}><Maximize2 size={18} /> Expand camera</button>
            </div>
          </div>

          <div className="notice notice-blue"><div><strong>Need help with face capture or blinking?</strong><p>Staff-assisted attendance is available, including for people with facial differences. An administrator or the assigned adviser can verify the school ID or official roster and record an audited attendance entry.</p>{auth.role() === 'admin' && <button className="btn-secondary" disabled={previewOnly} onClick={async () => {
            pauseRecognition();
            streamRef.current?.getTracks().forEach((track) => track.stop());
            setCameraOn(false);
            try { await pendingScanRef.current; } catch { /* Scan errors are shown by the scanner. */ }
            window.location.href = '/dashboard/attendance';
          }}>Open assisted attendance</button>}</div></div>

          {stationHealth?.recognition_model === false && <div className="notice notice-warning" role="alert"><div><strong>Face model unavailable on this computer.</strong><p>{stationHealth.recognition_message || 'Restore the encrypted model and matching key, or enroll authorized people and train a model here.'}</p></div></div>}

          {feedback && (
            <div className={`scan-feedback ${feedback.ok ? 'scan-success' : 'scan-warning'}`}>
              {feedback.ok ? <CheckCircle2 size={24} /> : <AlertTriangle size={24} />}
              <div><strong>{previewOnly ? 'Preview result - nothing saved' : testMode ? 'Camera test result' : feedback.batch ? 'Multi-face scan result' : feedback.ok ? 'Camera ready' : 'Attention'}</strong>
                <p>{feedback.message}</p>{feedback.reasons?.length > 0 && <details><summary>Capture details</summary><ul>{feedback.reasons.slice(0, 3).map(reason => <li key={reason}>{reason}</li>)}</ul></details>}{feedback.batch?.map((item, index) => <span className="muted-small" key={`${item.person?.id || index}-${item.distance}`}>{item.person?.full_name || `Unknown person ${index + 1}`}: {item.attendance_event?.recorded ? `${item.attendance_event.direction} · ${item.attendance_event.status}` : item.message}{testMode && ` · photo/video protection: disabled`} · {item.liveness_verified ? 'liveness verified' : 'liveness pending'} · {cameraIdentityScore(item)}</span>)}</div>
            </div>
          )}
        </section>

        {(testMode || previewOnly) ? <aside className="scanner-log"><div className="scanner-log-header"><h2>{previewOnly ? 'Session previews' : 'Session tests'}</h2></div><div className="scanner-log-list">{testRuns.length === 0 && <div className="empty-state"><p>{previewOnly ? 'No previews yet. Enable camera and start recognition.' : 'No tests run yet. Start with a live-person baseline, then test the photo.'}</p></div>}{testRuns.map(run => <div className="scan-log-item" key={run.id}><strong>{run.name}{run.replayAccepted ? ' — REPLAY PASSED' : ''}</strong><p>{run.message}</p>{run.details?.length > 0 && <details open><summary>Capture details</summary><ul>{run.details.map(detail => <li key={detail}>{detail}</li>)}</ul></details>}</div>)}</div><div className="scanner-log-footer">No results or camera frames are saved to the database.</div></aside> : <aside className="scanner-log">
          <div className="scanner-log-header"><div><p className="eyebrow">Today · {localDate()}</p><h2>Recent gate events</h2></div><Clock3 size={20} /></div>
          <div className="scanner-log-list">
            {events.length === 0 && <div className="empty-state"><Camera size={32} /><p>No gate events recorded today.</p></div>}
            {events.map((event) => <div className="scan-log-item" key={event.id}><div className="scan-log-top"><strong>{event.name}</strong><span>{displayTime(event.time)}</span></div><div className="scan-log-meta"><span className="tag tag-gray">{event.role}</span><span className={`tag ${event.status === 'Late' ? 'tag-warning' : 'tag-success'}`}>{event.direction} · {event.status}</span></div></div>)}
          </div>
          <div className="scanner-log-footer"><MessageSquareText size={17} /> {auth.role() === 'admin' ? `${outboxCount} notice(s) in SMS outbox` : 'SMS delivery is recorded by the server'}</div>
        </aside>}
      </main>
      {registrationOpen && <StudentRegistrationModal onClose={() => setRegistrationOpen(false)} onSaved={() => { setRegistrationOpen(false); refreshLog(); }} />}
    </div>
  );
}
