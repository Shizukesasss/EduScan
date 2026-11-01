import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Camera, CheckCircle2, Clock3, KeyRound, LayoutDashboard, LogOut, Maximize2, Minimize2, RefreshCw, ScanFace, UserPlus } from 'lucide-react';
import { api, auth, captureVideoFrame, localDate, enrollmentCapture } from '../../api/client';
import StudentRegistrationModal from '../../components/Scanner/StudentRegistrationModal';
import { cameraTestMatchMessage, cameraIdentityScore } from '../../services/enrollmentFeedback';

const attendanceLabel = event => event.direction === event.status ? event.direction : `${event.direction} · ${event.status}`;
const gateEventTime = value => {
  if (!value) return '—';
  const [hours, minutes, seconds = 0] = value.split(':').map(Number);
  const date = new Date();
  date.setHours(hours, minutes, seconds, 0);
  return date.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
};

export default function Scanner() {
  const [previewOnly] = useState(() => new URLSearchParams(window.location.search).get('preview') === '1');
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
    if (previewOnly) return;
    stationIdRef.current = localStorage.getItem('eduscan.stationId') || crypto.randomUUID();
    localStorage.setItem('eduscan.stationId', stationIdRef.current);
  }, [previewOnly]);
  const [cameraOn, setCameraOn] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [events, setEvents] = useState([]);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [cameraFullscreen, setCameraFullscreen] = useState(false);
  const [stationHealth, setStationHealth] = useState({ api: false, database: false, gateway_enabled: false, gateway_reachable: false, recognition_model: false, attendance_auto_visit_ready: false });
  const [backendReachable, setBackendReachable] = useState(true);
  const [testRuns, setTestRuns] = useState([]);

  const refreshLog = useCallback(() => {
    if (previewOnly) return;
    if (logBusyRef.current) return;
    logBusyRef.current = true;
    return api.get(`/gate/recent?date=${localDate()}`).then(setEvents).catch((err) => setFeedback({ ok: false, message: err.message }))
      .finally(() => { logBusyRef.current = false; });
  }, [previewOnly]);

  useEffect(() => { refreshLog(); }, [refreshLog]);
  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const result = await api.get('/station/health');
        if (mounted) {
          setStationHealth(result); setBackendReachable(true);
          if (result.recognition_model === false && scanningRef.current) {
            clearInterval(timerRef.current); scanningRef.current = false; scanGenerationRef.current += 1; setScanning(false);
            setFeedback({ ok: false, message: result.recognition_message || 'Restore or train the face model before recognition.' });
          }
          if (!previewOnly && result.attendance_auto_visit_ready !== true && scanningRef.current) {
            clearInterval(timerRef.current); scanningRef.current = false; scanGenerationRef.current += 1; setScanning(false);
            setFeedback({ ok: false, message: 'Restart the updated EduScan API before recording automatic attendance.' });
          }
        }
      }
      catch { if (mounted) setBackendReachable(false); }
    };
    check(); const timer = window.setInterval(check, 10000);
    return () => { mounted = false; clearInterval(timer); };
  }, [previewOnly]);
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
      setFeedback({ ok: true, message: 'Camera is ready. Start recognition when the gate lane is clear.' });
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraOn(false);
      setFeedback({ ok: false, message: `Camera could not start: ${err.message}` });
    }
  };

  const scanOnce = useCallback(async () => {
    if (!scanningRef.current || busyRef.current || !videoRef.current?.videoWidth) return;
    if (!previewOnly && stationHealth.attendance_auto_visit_ready !== true) {
      clearInterval(timerRef.current); scanningRef.current = false; scanGenerationRef.current += 1; setScanning(false);
      setFeedback({ ok: false, message: 'Restart the updated EduScan API before recording automatic attendance.' });
      return;
    }
    busyRef.current = true;
    const generation = scanGenerationRef.current;
    try {
      const form = new FormData();
      let lastFrame;
      const startedAt = videoRef.current.currentTime;
      // Capture enough closely spaced observations to catch a natural blink,
      // then perform one request instead of a cloud round trip per frame.
      const frameCount = 40;
      for (let index = 0; index < frameCount; index++) {
        if (!scanningRef.current || generation !== scanGenerationRef.current) return;
        const blob = await captureVideoFrame(videoRef.current, 0.9, enrollmentCapture.maxDimension);
        lastFrame = blob;
        form.append('frames', blob, `gate-${index}.jpg`);
        if (index < frameCount - 1) await new Promise(resolve => window.setTimeout(resolve, 100));
      }
      if (videoRef.current.currentTime <= startedAt || videoRef.current.paused) {
        throw new Error('The camera preview is not updating. Reconnect the camera before trying recognition again.');
      }
      if (!previewOnly) {
        form.append('frame', lastFrame, 'gate.jpg');
        form.append('station_id', stationIdRef.current);
      }
      if (!scanningRef.current || generation !== scanGenerationRef.current) return;
      const request = api.post(previewOnly ? '/biometrics/recognize-preview' : '/biometrics/recognize-many', form, { signal: AbortSignal.timeout(30000) });
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
      const recorded = batch.results.filter((item) => item.attendance_event?.recorded);
      const recognized = batch.results.filter((item) => item.recognized);
      const held = batch.results.filter(item => item.attendance_event?.presence_hold);
      const blocked = batch.results.filter(item => item.presentation_verified === false);
      setFeedback({ ok: recorded.length > 0 || held.length > 0, batch: batch.results,
        message: (held.length > 0 && recorded.length === 0 ? 'Attendance is already saved for this visit. Leave the camera view before scanning again.'
          : `${batch.face_count} face(s) detected · ${recognized.length} recognized · ${recorded.length} automatic attendance event(s) recorded.`)
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
      setFeedback({ ok: false, message: err.message });
    } finally {
      pendingScanRef.current = null; busyRef.current = false;
    }
  }, [refreshLog, previewOnly, stationHealth.attendance_auto_visit_ready]);

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
    if (stationHealth?.recognition_model === false) {
      setFeedback({ ok: false, message: stationHealth.recognition_message || 'Restore or train the face model before recognition.' });
      return;
    }
    if (!previewOnly && stationHealth.attendance_auto_visit_ready !== true) {
      setFeedback({ ok: false, message: 'Restart the updated EduScan API before recording automatic attendance.' });
      return;
    }
    scanningRef.current = true;
    setScanning(true);
    setFeedback({ ok: true, message: previewOnly ? 'Checking the camera view without saving attendance…' : 'Checking the current camera view for automatic attendance…' });
    scanOnce();
    timerRef.current = window.setInterval(scanOnce, 200);
  };

  const restartRecognition = () => {
    if (registrationOpen || !cameraOn) return;
    if (stationHealth?.recognition_model === false) {
      setFeedback({ ok: false, message: stationHealth.recognition_message || 'Restore or train the face model before recognition.' });
      return;
    }
    if (!previewOnly && stationHealth.attendance_auto_visit_ready !== true) {
      setFeedback({ ok: false, message: 'Restart the updated EduScan API before recording automatic attendance.' });
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
        <div className="brand-lockup"><img src="/logo.png" alt="San Jose National High School logo" /><div><h2>EduScan Gate Station</h2><span>{previewOnly ? 'Preview only · nothing is saved' : 'San Jose National High School · local biometric station'}</span></div></div>
        <div className="action-row">
          {auth.role() === 'admin' && (
            <>
              <button className="btn-secondary" onClick={() => window.location.href = '/dashboard'}><LayoutDashboard size={16} /> Dashboard</button>
              <button className="btn-secondary" disabled={previewOnly} title={previewOnly ? 'Open the normal scanner to enroll a person' : undefined} onClick={openEnrollment}><UserPlus size={16} /> Enroll person</button>
            </>
          )}
          <button className="icon-btn" title="Account security" aria-label="Account security" onClick={() => { window.location.href = '/account/security'; }}><KeyRound size={18} /><span className="control-label">Account security</span></button>
          {previewOnly && <a className="btn-secondary" href="/scanner">Open normal scanner</a>}
          <div className="scanner-state"><span className={`status-dot ${scanning ? '' : 'warning-dot'}`} /> {scanning ? previewOnly ? 'PREVIEW ACTIVE' : 'RECOGNITION ACTIVE' : cameraOn ? 'CAMERA READY' : 'CAMERA OFF'}</div>
          <button className="icon-btn" onClick={logout} title="Sign out"><LogOut size={18} /><span className="control-label">Sign out</span></button>
        </div>
      </header>

      <main className="scanner-main">
        <section className="scanner-stage">
          {previewOnly && <div className="notice notice-blue" role="status"><div><strong>Preview only</strong><p>This uses the main scanner's identity and configured blink checks. Keep both people visible and blink naturally. No attendance, SMS, review changes, enrollment, or camera frames are saved. Photo/video protection remains disabled in the restored flow.</p></div></div>}
          {scanning && !backendReachable && <div className="notice notice-danger scanner-backend-warning"><AlertTriangle size={22} /><div><strong>Attendance backend unavailable.</strong> Recognition is paused from recording attendance or SMS notices. Keep people at the gate and use the documented manual attendance fallback until the API is restored.</div></div>}
          <div className="station-health-strip"><span className={`tag ${backendReachable && stationHealth.database ? 'tag-success' : 'tag-danger'}`}>API / database: {backendReachable && stationHealth.database ? 'ready' : 'unavailable'}</span><span className={`tag ${cameraOn ? 'tag-success' : 'tag-gray'}`}>Camera: {cameraOn ? 'ready' : 'off'}</span><span className={`tag ${stationHealth.gateway_enabled && stationHealth.gateway_reachable ? 'tag-success' : 'tag-warning'}`}>SMS: {previewOnly ? 'disabled in preview' : stationHealth.gateway_enabled ? stationHealth.gateway_reachable ? 'reachable' : 'unreachable' : 'disabled'}</span><span className={`tag ${stationHealth.recognition_model ? 'tag-success' : 'tag-warning'}`}>LBPH: {stationHealth.recognition_model ? 'ready' : 'model missing'}</span></div>
          {!previewOnly && backendReachable && stationHealth.api && stationHealth.attendance_auto_visit_ready !== true && <div className="notice notice-warning" role="alert"><div><strong>Updated API required for attendance.</strong><p>Restart EduScan to enable automatic Time In and Time Out.</p></div></div>}
          <div className="camera-placeholder live-camera" ref={cameraFrameRef}>
            <video ref={videoRef} playsInline muted aria-label="Gate camera preview" />
            {!cameraOn && <div className="camera-frame"><Camera size={78} /><h1>Gate camera</h1><p>Camera frames are processed by the local LBPH server and are not uploaded to a cloud service.</p></div>}
            {scanning && <div className="multi-face-guide"><span>Multi-face scan area · up to five people facing the camera</span></div>}
            <button className="camera-fullscreen-toggle" onClick={toggleCameraFullscreen} title={cameraFullscreen ? 'Exit full-screen camera' : 'Open full-screen camera'}>
              {cameraFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              <span>{cameraFullscreen ? 'Exit full screen' : 'Full-screen camera'}</span>
            </button>
          </div>

          <div className="scanner-control-panel">
            <div><p className="eyebrow">{previewOnly ? 'Preview only' : 'Automatic attendance'}</p><h2>{cameraOn ? 'Multi-face recognition station' : 'Start the secured gate camera'}</h2><p>{previewOnly ? 'Recognition repeats in four-second captures using the main scanner flow. Each person must pass identity and configured blink checks. Nothing is saved. Pause recognition when finished.' : 'Up to five people can face the camera together. Each verified person is timed in on the first visit and timed out on the next visit after leaving the camera view. Brief missed detections keep the same visit open. Face the camera long enough to complete recognition and the configured blink check. Photo/video protection is disabled; use a live face directly.'}</p></div>
            <div className="scanner-control-actions">
              {!cameraOn ? <button className="btn-primary" onClick={startCamera}><Camera size={18} /> Enable camera</button>
                : <button className={scanning ? 'btn-secondary' : 'btn-primary'} disabled={!scanning && (!backendReachable || (!previewOnly && stationHealth.attendance_auto_visit_ready !== true) || stationHealth?.recognition_model === false)} onClick={toggleScanning}><ScanFace size={18} /> {scanning ? 'Pause recognition' : 'Start recognition'}</button>}
              {cameraOn && <button className="btn-secondary" disabled={!backendReachable || stationHealth?.recognition_model === false || (!previewOnly && stationHealth.attendance_auto_visit_ready !== true)} onClick={restartRecognition}><RefreshCw size={18} /> Restart recognition</button>}
            </div>
          </div>

          <div className="notice notice-blue"><div><strong>Need staff help with registration?</strong><p>An administrator can create or update the school record in People &amp; records, including when camera enrollment cannot be completed. After verifying the person's identity, staff can record an assisted visit in Attendance.</p>{auth.role() === 'admin' && <button className="btn-secondary" disabled={previewOnly} onClick={async () => {
            pauseRecognition();
            streamRef.current?.getTracks().forEach((track) => track.stop());
            setCameraOn(false);
            try { await pendingScanRef.current; } catch { /* Scan errors are shown by the scanner. */ }
            window.location.href = '/dashboard/administration?tab=people';
          }}>Open People &amp; records</button>}</div></div>

          {stationHealth?.recognition_model === false && <div className="notice notice-warning" role="alert"><div><strong>Face model unavailable on this computer.</strong><p>{stationHealth.recognition_message || 'Restore the encrypted model and matching key, or enroll authorized people and train a model here.'}</p></div></div>}

          {feedback && (
            <div className={`scan-feedback ${feedback.ok ? 'scan-success' : 'scan-warning'}`}>
              {feedback.ok ? <CheckCircle2 size={24} /> : <AlertTriangle size={24} />}
              <div><strong>{previewOnly ? 'Preview result - nothing saved' : feedback.batch ? 'Multi-face scan result' : feedback.ok ? 'Camera ready' : 'Attention'}</strong>
                <p>{feedback.message}</p>{feedback.reasons?.length > 0 && <details><summary>Capture details</summary><ul>{feedback.reasons.slice(0, 3).map(reason => <li key={reason}>{reason}</li>)}</ul></details>}{feedback.batch?.map((item, index) => <span className="muted-small" key={`${item.person?.id || index}-${item.distance}`}>{item.person?.full_name || `Unknown person ${index + 1}`}: {item.attendance_event?.recorded ? attendanceLabel(item.attendance_event) : item.message} · {item.liveness_verified ? 'liveness verified' : 'liveness pending'} · {cameraIdentityScore(item)}</span>)}</div>
            </div>
          )}
        </section>

        {previewOnly ? <aside className="scanner-log"><div className="scanner-log-header"><h2>Session previews</h2></div><div className="scanner-log-list">{testRuns.length === 0 && <div className="empty-state"><p>No previews yet. Enable camera and start recognition.</p></div>}{testRuns.map(run => <div className="scan-log-item" key={run.id}><strong>{run.name}</strong><p>{run.message}</p>{run.details?.length > 0 && <details open><summary>Capture details</summary><ul>{run.details.map(detail => <li key={detail}>{detail}</li>)}</ul></details>}</div>)}</div><div className="scanner-log-footer">No results or camera frames are saved to the database.</div></aside> : <aside className="scanner-log">
          <div className="scanner-log-header"><div><p className="eyebrow">Today · {localDate()}</p><h2>Recent gate events</h2></div><Clock3 size={20} /></div>
          <div className="scanner-log-list">
            {events.length === 0 && <div className="empty-state"><Camera size={32} /><p>No gate events recorded today.</p></div>}
            {events.map((event) => <div className="scan-log-item" key={event.id}><div className="scan-log-top"><strong>{event.name}</strong><span>{gateEventTime(event.time)}</span></div><div className="scan-log-meta"><span className="tag tag-gray">{event.role}</span><span className={`tag ${event.status === 'Late' ? 'tag-warning' : 'tag-success'}`}>{attendanceLabel(event)}</span></div></div>)}
          </div>
          <div className="scanner-log-footer">{auth.role() === 'admin' ? <a href="/dashboard/setup#sms-delivery">Review SMS delivery in System Setup</a> : 'SMS delivery is recorded by the server'}</div>
        </aside>}
      </main>
      {registrationOpen && <StudentRegistrationModal onClose={() => setRegistrationOpen(false)} onSaved={() => { setRegistrationOpen(false); refreshLog(); }} />}
    </div>
  );
}
