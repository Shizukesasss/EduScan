import { useCallback, useEffect, useRef, useState } from 'react';
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

  const stopCamera = () => {
    pauseRecognition();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
    setFeedback({ ok: true, message: 'Gate camera turned off.' });
  };

  const handleCameraStatusToggle = () => {
    if (cameraOn) stopCamera();
    else void startCamera();
  };

  const [clockNow, setClockNow] = useState(() => new Date());
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [confirmingSignOut, setConfirmingSignOut] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const accountMenuRef = useRef(null);
  const accountTriggerRef = useRef(null);
  const accountItemsRef = useRef([]);
  const mobileMenuRef = useRef(null);

  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const onPointerDown = (event) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(event.target)) {
        setAccountMenuOpen(false);
        setConfirmingSignOut(false);
      }
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(event.target)) {
        setMobileMenuOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        if (accountMenuOpen) {
          setAccountMenuOpen(false);
          setConfirmingSignOut(false);
          accountTriggerRef.current?.focus();
        }
        if (mobileMenuOpen) {
          setMobileMenuOpen(false);
        }
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [accountMenuOpen, mobileMenuOpen]);

  const focusAccountItem = (index) => {
    const items = accountItemsRef.current.filter(Boolean);
    if (!items.length) return;
    const target = items[(index + items.length) % items.length];
    target?.focus();
  };

  const handleAccountTriggerKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setAccountMenuOpen(true);
      const targetIndex = event.key === 'ArrowUp' ? 1 : 0;
      window.requestAnimationFrame(() => focusAccountItem(targetIndex));
    }
  };

  const handleAccountMenuKeyDown = (event) => {
    const items = accountItemsRef.current.filter(Boolean);
    const currentIndex = items.indexOf(document.activeElement);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusAccountItem(currentIndex + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      focusAccountItem(currentIndex - 1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      focusAccountItem(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      focusAccountItem(items.length - 1);
    }
  };

  const operatorName = auth.name() || 'Gate Operator';
  const operatorInitials = operatorName
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || 'G';
  const operatorRoleLabel = auth.role() === 'admin' ? 'Administrator' : 'Gate Station';

  const today = localDate();
  const formattedStationDate = new Date(`${today}T12:00:00`).toLocaleDateString('en-PH', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const formattedStationTime = clockNow.toLocaleTimeString('en-PH', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  });

  const scannerStatusTone = scanning
    ? 'is-active'
    : cameraOn
      ? 'is-ready'
      : 'is-standby';

  const timeInCount = events.filter((e) => e.direction === 'Time In').length;
  const timeOutCount = events.filter((e) => e.direction === 'Time Out').length;

  return (
    <div className="scanner-shell">
      <header className="scanner-header">
        <div className="scanner-header__inner">
          {/* Zone 1: Brand (Left) */}
          <div className="scanner-header__brand">
            <img
              src="/logo.png"
              width="40"
              height="40"
              alt="San Jose National High School logo"
              className="scanner-header__logo"
            />
            <div className="scanner-header__brand-text">
              <h2 className="scanner-header__title">
                <span className="scanner-header__title-full">EduScan Gate Station</span>
                <span className="scanner-header__title-short">EduScan Gate</span>
              </h2>
              <span
                className="scanner-header__subtitle"
                title={
                  previewOnly
                    ? 'Preview only · nothing is saved'
                    : 'San Jose National High School · Local biometric station'
                }
              >
                {previewOnly
                  ? 'Preview only · nothing is saved'
                  : 'San Jose National High School · Local biometric station'}
              </span>
            </div>
          </div>

          {/* Zone 2: Live Status & Clock (Center) */}
          <div className="scanner-header__center">
            <div className="scanner-clock" aria-label="Station live clock and date">
              <time className="scanner-clock__time">{formattedStationTime}</time>
              <span className="scanner-clock__date">{formattedStationDate}</span>
            </div>

            <span className="scanner-header__divider" aria-hidden="true" />

            <div className="scanner-status-group" role="status" aria-live="polite">
              <button
                type="button"
                className={`scanner-status-chip ${cameraOn ? 'is-online' : 'is-offline'}`}
                onClick={handleCameraStatusToggle}
                title={cameraOn ? 'Click to turn off gate camera' : 'Click to enable gate camera'}
                aria-label={
                  cameraOn
                    ? scanning
                      ? 'Camera on and scanning — click to turn off camera'
                      : 'Camera on — click to turn off camera'
                    : 'Camera off — click to enable camera'
                }
              >
                <span className="scanner-status-chip__dot" aria-hidden="true" />
                <span className="scanner-status-chip__label">
                  {cameraOn ? (scanning ? 'Camera scanning' : 'Camera on') : 'Camera off'}
                </span>
              </button>

              <span
                className={`scanner-status-chip is-readonly ${backendReachable ? 'is-online' : 'is-warning'}`}
                title={
                  backendReachable
                    ? 'Connected to local EduScan server'
                    : 'Backend unreachable — scans paused until connection is restored'
                }
              >
                <span className="scanner-status-chip__dot" aria-hidden="true" />
                <span className="scanner-status-chip__label">
                  {backendReachable ? 'Online' : 'Offline — queued'}
                </span>
              </span>
            </div>
          </div>

          {/* Zone 3: Actions (Right) */}
          <div className="scanner-header__actions">
            {auth.role() === 'admin' && (
              <>
                <button
                  type="button"
                  className="btn-secondary scanner-action-btn scanner-action-btn--secondary"
                  title="Return to Administrator Dashboard"
                  aria-label="Dashboard"
                  onClick={() => {
                    window.location.href = '/dashboard';
                  }}
                >
                  <span className="scanner-action-btn__label">Dashboard</span>
                </button>
                <button
                  type="button"
                  className="btn-primary scanner-action-btn scanner-action-btn--primary"
                  disabled={previewOnly}
                  title={previewOnly ? 'Open the normal scanner to enroll a person' : 'Enroll a student or staff member'}
                  onClick={openEnrollment}
                >
                  <span className="scanner-action-btn__label">Enroll person</span>
                </button>
              </>
            )}

            {previewOnly && (
              <a
                className="btn-secondary scanner-action-btn scanner-action-btn--secondary"
                href="/scanner"
                title="Switch to normal attendance scanner"
              >
                <span className="scanner-action-btn__label">Normal scanner</span>
              </a>
            )}

            {/* User / Account Dropdown */}
            <div className="scanner-user-menu" ref={accountMenuRef}>
              <button
                ref={accountTriggerRef}
                type="button"
                className={`scanner-user-trigger${accountMenuOpen ? ' is-open' : ''}`}
                aria-haspopup="menu"
                aria-expanded={accountMenuOpen}
                aria-label={`Account menu for ${operatorName}`}
                title={`${operatorName} (${operatorRoleLabel})`}
                onClick={() => {
                  setAccountMenuOpen((prev) => {
                    const next = !prev;
                    if (!next) setConfirmingSignOut(false);
                    return next;
                  });
                }}
                onKeyDown={handleAccountTriggerKeyDown}
              >
                <span className="scanner-user-trigger__avatar" aria-hidden="true">
                  {operatorInitials}
                </span>
                <span className="scanner-user-trigger__name">{operatorName}</span>
              </button>

              {accountMenuOpen && (
                <div
                  className="scanner-user-dropdown"
                  role="menu"
                  aria-label="Station account actions"
                  onKeyDown={handleAccountMenuKeyDown}
                >
                  <div className="scanner-user-dropdown__header">
                    <strong>{operatorName}</strong>
                    <span>{operatorRoleLabel}</span>
                  </div>
                  <div className="scanner-user-dropdown__divider" role="separator" />
                  <button
                    ref={(el) => {
                      accountItemsRef.current[0] = el;
                    }}
                    type="button"
                    role="menuitem"
                    className="scanner-user-dropdown__item"
                    onClick={() => {
                      setAccountMenuOpen(false);
                      window.location.href = '/account/security';
                    }}
                  >
                    <span>Account security</span>
                  </button>
                  <div className="scanner-user-dropdown__divider" role="separator" />
                  {!confirmingSignOut ? (
                    <button
                      ref={(el) => {
                        accountItemsRef.current[1] = el;
                      }}
                      type="button"
                      role="menuitem"
                      className="scanner-user-dropdown__item is-danger"
                      onClick={() => setConfirmingSignOut(true)}
                    >
                      <span>Sign out</span>
                    </button>
                  ) : (
                    <div className="scanner-signout-confirm" role="group" aria-label="Confirm sign out">
                      <p className="scanner-signout-confirm__prompt">Sign out of this gate station?</p>
                      <div className="scanner-signout-confirm__actions">
                        <button
                          type="button"
                          className="btn-secondary scanner-signout-confirm__btn"
                          onClick={() => setConfirmingSignOut(false)}
                        >
                          Cancel
                        </button>
                        <button
                          ref={(el) => {
                            accountItemsRef.current[1] = el;
                          }}
                          type="button"
                          className="btn-danger scanner-signout-confirm__btn is-confirm"
                          onClick={logout}
                        >
                          Sign out
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Mobile Menu Toggle (< 640px) */}
            <div className="scanner-mobile-menu" ref={mobileMenuRef}>
              <button
                type="button"
                className="scanner-mobile-toggle"
                aria-label={mobileMenuOpen ? 'Close station menu' : 'Open station menu'}
                aria-expanded={mobileMenuOpen}
                title={mobileMenuOpen ? 'Close menu' : 'Station menu'}
                onClick={() => {
                  setMobileMenuOpen((prev) => !prev);
                  setConfirmingSignOut(false);
                }}
              >
                {mobileMenuOpen ? 'Close menu' : 'Menu'}
              </button>

              {mobileMenuOpen && (
                <div className="scanner-mobile-sheet" role="dialog" aria-label="Gate station menu">
                  <div className="scanner-mobile-sheet__status">
                    <button
                      type="button"
                      className={`scanner-status-chip ${cameraOn ? 'is-online' : 'is-offline'}`}
                      onClick={handleCameraStatusToggle}
                    >
                      <span className="scanner-status-chip__dot" aria-hidden="true" />
                      <span>{cameraOn ? 'Camera on' : 'Camera off'}</span>
                    </button>
                    <span className={`scanner-status-chip is-readonly ${backendReachable ? 'is-online' : 'is-warning'}`}>
                      <span className="scanner-status-chip__dot" aria-hidden="true" />
                      <span>{backendReachable ? 'Online' : 'Offline — queued'}</span>
                    </span>
                  </div>

                  <div className="scanner-user-dropdown__divider" role="separator" />

                  <div className="scanner-mobile-sheet__actions">
                    {auth.role() === 'admin' && (
                      <>
                        <button
                          type="button"
                          className="btn-primary scanner-action-btn scanner-action-btn--primary"
                          disabled={previewOnly}
                          onClick={() => {
                            setMobileMenuOpen(false);
                            openEnrollment();
                          }}
                        >
                          <span>Enroll person</span>
                        </button>
                        <button
                          type="button"
                          className="btn-secondary scanner-action-btn scanner-action-btn--secondary"
                          onClick={() => {
                            window.location.href = '/dashboard';
                          }}
                        >
                          <span>Dashboard</span>
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="scanner-user-dropdown__item"
                      onClick={() => {
                        window.location.href = '/account/security';
                      }}
                    >
                      <span>Account security</span>
                    </button>
                    {!confirmingSignOut ? (
                      <button
                        type="button"
                        className="scanner-user-dropdown__item is-danger"
                        onClick={() => setConfirmingSignOut(true)}
                      >
                        <span>Sign out</span>
                      </button>
                    ) : (
                      <div className="scanner-signout-confirm">
                        <p className="scanner-signout-confirm__prompt">Sign out of this gate station?</p>
                        <div className="scanner-signout-confirm__actions">
                          <button
                            type="button"
                            className="btn-secondary scanner-signout-confirm__btn"
                            onClick={() => setConfirmingSignOut(false)}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="btn-danger scanner-signout-confirm__btn is-confirm"
                            onClick={logout}
                          >
                            Sign out
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="scanner-main">
        <section className="scanner-stage" aria-label="Gate camera and recognition controls">
          {previewOnly && (
            <div className="notice notice-blue" role="status">
              <div>
                <strong>Preview only</strong>
                <p>
                  This uses the main scanner&apos;s identity and configured blink checks. Keep both people visible and blink naturally. No attendance, SMS, review changes, enrollment, or camera frames are saved. Photo/video protection remains disabled in the restored flow.
                </p>
              </div>
            </div>
          )}

          {scanning && !backendReachable && (
            <div className="notice notice-danger scanner-backend-warning">
              <div>
                <strong>Attendance backend unavailable.</strong> Recognition is paused from recording attendance or SMS notices. Keep people at the gate and use the documented manual attendance fallback until the API is restored.
              </div>
            </div>
          )}

          {!previewOnly && backendReachable && stationHealth.api && stationHealth.attendance_auto_visit_ready !== true && (
            <div className="notice notice-warning" role="alert">
              <div>
                <strong>Updated API required for attendance.</strong>
                <p>Restart EduScan to enable automatic Time In and Time Out.</p>
              </div>
            </div>
          )}

          {stationHealth?.recognition_model === true && stationHealth.recognition_code === 'ready_with_missing_enrollments' && (
            <div className="notice notice-warning" role="status">
              <div>
                <strong>Some face enrollments unavailable.</strong>
                <p>{stationHealth.recognition_message}</p>
              </div>
            </div>
          )}

          {stationHealth?.recognition_model === false && (
            <div className="notice notice-warning" role="alert">
              <div>
                <strong>Face model unavailable on this computer.</strong>
                <p>
                  {stationHealth.recognition_message ||
                    'Restore the encrypted model and matching key, or enroll authorized people and train a model here.'}
                </p>
              </div>
            </div>
          )}

          <div
            className={`camera-placeholder live-camera${scanning ? ' is-scanning' : ''}${cameraOn ? ' is-camera-on' : ''}`}
            ref={cameraFrameRef}
          >
            <video ref={videoRef} playsInline muted aria-label="Gate camera preview" />

            <div className="camera-hud-top">
              <span className={`camera-hud-badge ${scannerStatusTone}`}>
                <span className="camera-hud-badge__dot" aria-hidden="true" />
                {scanning
                  ? previewOnly
                    ? 'Live preview scan'
                    : 'Live gate recognition'
                  : cameraOn
                    ? 'Camera feed active · recognition paused'
                    : 'Camera standby'}
              </span>

              <button
                type="button"
                className="camera-fullscreen-toggle"
                onClick={toggleCameraFullscreen}
                title={cameraFullscreen ? 'Exit full-screen camera' : 'Open full-screen camera'}
              >
                <span>{cameraFullscreen ? 'Exit full screen' : 'Full-screen camera'}</span>
              </button>
            </div>

            {!cameraOn && (
              <div className="camera-frame">
                <div className="camera-standby-card">
                  <h1>Gate camera is on standby</h1>
                  <p>
                    Camera frames are processed locally by the on-premise LBPH recognition server and are never uploaded to an external cloud service.
                  </p>
                  <div className="camera-standby-pills" aria-hidden="true">
                    <span>Local LBPH processing</span>
                    <span>Up to 5 faces</span>
                    <span>Blink liveness check</span>
                  </div>
                  <button type="button" className="btn-primary camera-frame__cta" onClick={startCamera}>
                    <span>Enable gate camera</span>
                  </button>
                </div>
              </div>
            )}

            {scanning && (
              <div className="multi-face-guide">
                <span>Multi-face scan area · up to five people facing the camera</span>
              </div>
            )}
          </div>

          {feedback && (
            <div className={`scan-feedback ${feedback.ok ? 'scan-success' : 'scan-warning'}`} role="status">
              <div className="scan-feedback__body">
                <strong>
                  {previewOnly
                    ? 'Preview result — nothing saved'
                    : feedback.batch
                      ? 'Multi-face scan result'
                      : feedback.ok
                        ? 'Camera ready'
                        : 'Attention'}
                </strong>
                <p>{feedback.message}</p>
                {feedback.reasons?.length > 0 && (
                  <details className="scan-feedback__details">
                    <summary>Capture details</summary>
                    <ul>
                      {feedback.reasons.slice(0, 3).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {feedback.batch?.length > 0 && (
                  <div className="scan-feedback__batch">
                    {feedback.batch.map((item, index) => (
                      <span
                        className="scan-feedback__person-chip muted-small"
                        key={`${item.person?.id || index}-${item.distance}`}
                      >
                        <strong>{item.person?.full_name || `Unknown person ${index + 1}`}</strong>:{' '}
                        {item.attendance_event?.recorded ? attendanceLabel(item.attendance_event) : item.message} ·{' '}
                        {item.liveness_verified ? 'liveness verified' : 'liveness pending'} ·{' '}
                        {cameraIdentityScore(item)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="scanner-control-panel">
            <div className="scanner-control-panel__copy">
              <p className="eyebrow">{previewOnly ? 'Preview only' : 'Automatic attendance'}</p>
              <h2>{cameraOn ? 'Multi-face recognition station' : 'Start the secured gate camera'}</h2>
              <p>
                {previewOnly
                  ? 'Recognition repeats in four-second captures using the main scanner flow. Each person must pass identity and configured blink checks. Nothing is saved. Pause recognition when finished.'
                  : 'Up to five people can face the camera together. Each verified person is timed in on the first visit and timed out on the next visit after leaving the camera view. Face the camera long enough to complete recognition and the configured blink check.'}
              </p>
            </div>
            <div className="scanner-control-actions">
              {!cameraOn ? (
                <button type="button" className="btn-primary scanner-control-btn" onClick={startCamera}>
                  <span>Enable camera</span>
                </button>
              ) : (
                <button
                  type="button"
                  className={`${scanning ? 'btn-secondary' : 'btn-primary'} scanner-control-btn`}
                  disabled={
                    !scanning &&
                    (!backendReachable ||
                      (!previewOnly && stationHealth.attendance_auto_visit_ready !== true) ||
                      stationHealth?.recognition_model === false)
                  }
                  onClick={toggleScanning}
                >
                  <span>{scanning ? 'Pause recognition' : 'Start recognition'}</span>
                </button>
              )}
              {cameraOn && (
                <button
                  type="button"
                  className="btn-secondary scanner-control-btn"
                  disabled={
                    !backendReachable ||
                    stationHealth?.recognition_model === false ||
                    (!previewOnly && stationHealth.attendance_auto_visit_ready !== true)
                  }
                  onClick={restartRecognition}
                >
                  <span>Restart recognition</span>
                </button>
              )}
            </div>
          </div>

          <div className="notice notice-blue scanner-assist-banner">
            <div className="scanner-assist-banner__copy">
              <strong>Need staff help with registration?</strong>
              <p>
                An administrator can create or update the school record in People &amp; records, including when camera enrollment cannot be completed. After verifying the person&apos;s identity, staff can record an assisted visit in Attendance.
              </p>
            </div>
            {auth.role() === 'admin' && (
              <button
                type="button"
                className="btn-secondary scanner-assist-banner__btn"
                disabled={previewOnly}
                onClick={async () => {
                  pauseRecognition();
                  streamRef.current?.getTracks().forEach((track) => track.stop());
                  setCameraOn(false);
                  try {
                    await pendingScanRef.current;
                  } catch {
                    /* Scan errors are shown by the scanner. */
                  }
                  window.location.href = '/dashboard/administration?tab=people';
                }}
              >
                Open People &amp; records
              </button>
            )}
          </div>
        </section>

        {previewOnly ? (
          <aside className="scanner-log" aria-label="Session previews">
            <div className="scanner-log-header">
              <div>
                <p className="eyebrow">Diagnostic mode</p>
                <h2>Session previews</h2>
              </div>
              <span className="scanner-log-count">{testRuns.length}</span>
            </div>
            <div className="scanner-log-list">
              {testRuns.length === 0 && (
                <div className="empty-state">
                  <strong>No previews yet</strong>
                  <p>Enable the gate camera and start recognition to test matching.</p>
                </div>
              )}
              {testRuns.map((run) => (
                <div className="scan-log-item" key={run.id}>
                  <strong>{run.name}</strong>
                  <p>{run.message}</p>
                  {run.details?.length > 0 && (
                    <details open>
                      <summary>Capture details</summary>
                      <ul>
                        {run.details.map((detail) => (
                          <li key={detail}>{detail}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              ))}
            </div>
            <div className="scanner-log-footer">No results or camera frames are saved to the database.</div>
          </aside>
        ) : (
          <aside className="scanner-log" aria-label="Recent gate events">
            <div className="scanner-log-header">
              <div>
                <p className="eyebrow">Today · {today}</p>
                <h2>Recent gate events</h2>
              </div>
              <div className="scanner-log-header__badge" title="Total gate events shown">
                <span>{events.length}</span>
              </div>
            </div>

            {events.length > 0 && (
              <div className="scanner-log-summary" aria-label="Gate event breakdown">
                <div className="scanner-log-summary__item">
                  <span>Time In</span>
                  <strong>{timeInCount}</strong>
                </div>
                <div className="scanner-log-summary__item">
                  <span>Time Out</span>
                  <strong>{timeOutCount}</strong>
                </div>
              </div>
            )}

            <div className="scanner-log-list">
              {events.length === 0 && (
                <div className="empty-state">
                  <strong>No gate events recorded today</strong>
                  <p>Verified arrivals and departures will appear here in real time.</p>
                </div>
              )}
              {events.map((event) => {
                const isLate = event.status === 'Late';
                const isTimeOut = event.direction === 'Time Out';
                const initial = String(event.name || 'P').trim().charAt(0).toUpperCase();
                return (
                  <div
                    className={`scan-log-item ${isLate ? 'is-late' : isTimeOut ? 'is-timeout' : 'is-present'}`}
                    key={event.id}
                  >
                    <div className="scan-log-top">
                      <div className="scan-log-person">
                        <span className="scan-log-avatar" aria-hidden="true">{initial}</span>
                        <strong>{event.name}</strong>
                      </div>
                      <time className="scan-log-time">{gateEventTime(event.time)}</time>
                    </div>
                    <div className="scan-log-meta">
                      <span className="tag tag-gray">{event.role}</span>
                      <span className={`tag ${isLate ? 'tag-warning' : 'tag-success'}`}>
                        {attendanceLabel(event)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="scanner-log-footer">
              {auth.role() === 'admin' ? (
                <a href="/dashboard/setup#sms-delivery">Review SMS delivery in System Setup</a>
              ) : (
                'SMS delivery is recorded by the server'
              )}
            </div>
          </aside>
        )}
      </main>
      {registrationOpen && (
        <StudentRegistrationModal
          onClose={() => setRegistrationOpen(false)}
          onSaved={() => {
            setRegistrationOpen(false);
            refreshLog();
          }}
        />
      )}
    </div>
  );
}
