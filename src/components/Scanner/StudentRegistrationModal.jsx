import { useEffect, useRef, useState } from 'react';
import { X, Camera, ScanFace, CheckCircle, Database, AlertTriangle } from 'lucide-react';
import { api, captureVideoFrame } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';

const targetFrames = 20;

export default function StudentRegistrationModal({ onClose, onSaved, person = null }) {
  const isReplacement = Boolean(person?.person_id);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [frames, setFrames] = useState([]);
  const [cameraOn, setCameraOn] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [saving, setSaving] = useState(false);
  const { showSuccess, showError } = useToast();
  const [personId, setPersonId] = useState(person?.person_id || null);
  const [form, setForm] = useState({ external_id: '', lrn: '', surname: '', first_name: '', middle_name: '', name_extension: '', sex: 'Male', role: 'Student', grade: '10', section: 'Rizal', assignment: '', guardian_phone: '', biometric_consent: false });
  const [changeReason, setChangeReason] = useState('');

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  const patch = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 960 }, height: { ideal: 720 } }, audio: false });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCameraOn(true);
    } catch (err) { showError(`Camera could not start: ${err.message}`); }
  };

  const captureDataset = async () => {
    setFrames([]); setIsCapturing(true);
    const collected = [];
    try {
      for (let index = 0; index < targetFrames; index += 1) {
        collected.push(await captureVideoFrame(videoRef.current, 0.92));
        setFrames([...collected]);
        await new Promise((resolve) => window.setTimeout(resolve, 220));
      }
      showSuccess(`${collected.length} real camera frames captured. The server will quality-check each face before training.`);
    } catch (err) { showError(err.message); }
    finally { setIsCapturing(false); }
  };

  const saveAndTrain = async () => {
    if (!(isReplacement ? person.biometric_consent : form.biometric_consent)) return showError('Confirm the documented consent/authorization before biometric enrollment.');
    if (isReplacement && changeReason.trim().length < 8) return showError('Enter a specific re-enrollment reason of at least 8 characters.');
    if (frames.length < targetFrames) return showError(`Capture all ${targetFrames} camera frames first.`);
    setSaving(true);
    try {
      let id = personId;
      if (!id) {
        const payload = { ...form, lrn: form.lrn || null, guardian_phone: form.guardian_phone || null, grade: form.role === 'Student' ? form.grade : null, section: form.role === 'Student' ? form.section : null, assignment: form.role === 'Student' ? null : form.assignment || null };
        const person = await api.post('/persons', payload);
        id = person.id;
        setPersonId(id);
      }
      const multipart = new FormData();
      frames.forEach((frame, index) => multipart.append('frames', frame, `enrollment-${index + 1}.jpg`));
      multipart.append('reason', isReplacement ? changeReason.trim() : 'Initial facial enrollment at gate station');
      const result = isReplacement
        ? await api.put(`/biometrics/enrollments/${id}`, multipart)
        : await api.post(`/biometrics/enrollments/${id}`, multipart);
      showSuccess(`${result.accepted} quality samples encrypted and saved. LBPH model ${result.model.version} trained for ${result.model.person_count} person(s).`);
      window.setTimeout(() => onSaved?.(result), 1800);
    } catch (err) { showError(`${err.message}${personId ? ' You can capture again and retry enrollment for this registered person.' : ''}`); }
    finally { setSaving(false); }
  };

  return (
    <div className="modal-backdrop"><div className="modal-card enrollment-modal">
      <div className="modal-header"><div><p className="eyebrow">Encrypted local dataset</p><h2><ScanFace size={24} /> {isReplacement ? 'Replace facial enrollment' : 'Enroll person & train LBPH'}</h2></div><button onClick={onClose} className="icon-btn"><X size={22} /></button></div>
      <div className="enrollment-content">
        {isReplacement ? <div className="enrollment-fields">
          <div className="enrollment-identity"><span>Authorized person</span><strong>{person.full_name}</strong><small>{person.external_id} · {person.role}{person.grade ? ` · Grade ${person.grade} — ${person.section}` : ''}</small></div>
          <div className="notice notice-warning"><AlertTriangle size={18} /><span>The current encrypted samples will be securely replaced after the new dataset passes quality checks. The audit history remains.</span></div>
          <label><span className="field-label">Required re-enrollment reason</span><textarea className="text-area" placeholder="Example: Appearance changed and recognition accuracy was verified as poor" value={changeReason} onChange={(event) => setChangeReason(event.target.value)} /></label>
        </div> : <div className="form-grid two-columns enrollment-fields">
          <label><span className="field-label">School ID / employee ID</span><input className="input-field" value={form.external_id} onChange={(e) => patch('external_id', e.target.value)} required /></label>
          <label><span className="field-label">LRN (students)</span><input className="input-field" value={form.lrn} onChange={(e) => patch('lrn', e.target.value)} /></label>
          <label><span className="field-label">Last name</span><input className="input-field" value={form.surname} onChange={(e) => patch('surname', e.target.value)} required /></label>
          <label><span className="field-label">First name</span><input className="input-field" value={form.first_name} onChange={(e) => patch('first_name', e.target.value)} required /></label>
          <label><span className="field-label">Middle name</span><input className="input-field" value={form.middle_name} onChange={(e) => patch('middle_name', e.target.value)} /></label>
          <label><span className="field-label">Extension (e.g., Jr.)</span><input className="input-field" value={form.name_extension} onChange={(e) => patch('name_extension', e.target.value)} /></label>
          <label><span className="field-label">Sex for official roster</span><select className="input-field" value={form.sex} onChange={(e) => patch('sex', e.target.value)}><option>Male</option><option>Female</option></select></label>
          <label><span className="field-label">Personnel group</span><select className="input-field" value={form.role} onChange={(e) => patch('role', e.target.value)}><option>Student</option><option>Faculty</option><option>Non-teaching Personnel</option></select></label>
          {form.role === 'Student' ? <><label><span className="field-label">Grade</span><input className="input-field" value={form.grade} onChange={(e) => patch('grade', e.target.value)} /></label><label><span className="field-label">Section</span><input className="input-field" value={form.section} onChange={(e) => patch('section', e.target.value)} /></label><label className="full-field"><span className="field-label">Parent/guardian mobile number</span><input className="input-field" placeholder="+639XXXXXXXXX" value={form.guardian_phone} onChange={(e) => patch('guardian_phone', e.target.value)} /></label></>
            : <label className="full-field"><span className="field-label">Office / assignment</span><input className="input-field" value={form.assignment} onChange={(e) => patch('assignment', e.target.value)} /></label>}
          <label className="checkbox-field full-field"><input type="checkbox" checked={form.biometric_consent} onChange={(e) => patch('biometric_consent', e.target.checked)} /><span>I confirm the school has documented the applicable consent/authorization and provided the privacy notice for this person.</span></label>
        </div>}
        <div className="enrollment-camera">
          <div className="enrollment-video"><video ref={videoRef} playsInline muted />{!cameraOn && <Camera size={48} />}{isCapturing && <div className="capture-indicator">CAPTURING</div>}{frames.length === targetFrames && !isCapturing && <CheckCircle className="capture-complete" size={48} />}</div>
          <div><div className="scan-log-top"><strong>Camera frames</strong><span>{frames.length}/{targetFrames}</span></div><div className="weight-meter weight-valid"><span style={{ width: `${frames.length / targetFrames * 100}%` }} /></div><p className="muted-small">Look forward, then slowly turn and tilt your head while keeping one face in view.</p></div>
          {!cameraOn ? <button className="btn-primary" onClick={startCamera}><Camera size={16} /> Enable camera</button> : <button className="btn-secondary" onClick={captureDataset} disabled={isCapturing}>{isCapturing ? 'Capturing real frames…' : 'Capture enrollment frames'}</button>}
        </div>
      </div>
      <div className="modal-actions"><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={saveAndTrain} disabled={saving || frames.length < targetFrames}><Database size={16} /> {saving ? 'Quality-checking & training…' : isReplacement ? 'Replace samples & retrain model' : 'Save encrypted samples & train model'}</button></div>
    </div></div>
  );
}
