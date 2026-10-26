import BiometricConsent from './BiometricConsent';
import EnrollmentFields from './EnrollmentFields';
import PhoneNumberField from './PhoneNumberField';
import { useEffect, useMemo, useRef, useState } from 'react';
import { X, Camera, ScanFace, CheckCircle, Database, AlertTriangle } from 'lucide-react';
import { api, captureVideoFrame, enrollmentCapture } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { normalizeGradeName } from '../../services/academicContext';
import { buildEnrollmentFeedback } from '../../services/enrollmentFeedback';

const targetFrames = enrollmentCapture.frames;
const personNamePattern = "[\\p{L}\\p{M} '’.-]+";
const isValidPersonName = (value) => /^[\p{L}\p{M} '’.-]+$/u.test(value.trim());

export default function StudentRegistrationModal({ onClose, onSaved, person = null }) {
  const isExistingPerson = Boolean(person?.person_id);
  const isReplacement = isExistingPerson && Number(person.sample_count) > 0;
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const cameraGeneration = useRef(0);
  const [frames, setFrames] = useState([]);
  const [cameraOn, setCameraOn] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [assistedRegistration, setAssistedRegistration] = useState(false);
  const [enrollmentError, setEnrollmentError] = useState(null);
  const { showSuccess, showError } = useToast();
  const [personId, setPersonId] = useState(person?.person_id || null);
  const [academicStructure, setAcademicStructure] = useState({ grade_levels: [], sections: [] });
  const [academicLoading, setAcademicLoading] = useState(!isExistingPerson);
  const [academicError, setAcademicError] = useState('');
  const [gradeLevelId, setGradeLevelId] = useState('');
  const [form, setForm] = useState({ external_id: '', lrn: '', surname: '', first_name: '', middle_name: '', name_extension: '', sex: 'Male', role: 'Student', date_of_birth: '', grade: '', section: '', school_year_id: '', assignment: '', guardian_phone: '', biometric_consent: false, enrollment_status: 'Regular', enrollment_note: '', enrollment_start_date: '', enrollment_end_date: '', transfer_school: '' });
  const [changeReason, setChangeReason] = useState('');

  useEffect(() => () => {
    cameraGeneration.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);
  useEffect(() => {
    if (isExistingPerson) return undefined;
    let stopped = false;
    api.get('/admin/academic-structure')
      .then((data) => { if (!stopped) setAcademicStructure(data); })
      .catch((error) => { if (!stopped) setAcademicError(error.message); })
      .finally(() => { if (!stopped) setAcademicLoading(false); });
    return () => { stopped = true; };
  }, [isExistingPerson]);

  const sortedGrades = useMemo(() => (academicStructure.grade_levels || [])
    .filter((grade) => grade.active)
    .sort((a, b) => {
      const gradeA = Number(normalizeGradeName(a.name));
      const gradeB = Number(normalizeGradeName(b.name));
      return Number.isFinite(gradeA) && Number.isFinite(gradeB) ? gradeA - gradeB : a.name.localeCompare(b.name);
    }), [academicStructure.grade_levels]);
  const availableSections = useMemo(() => (academicStructure.sections || [])
    .filter((section) => section.active && section.grade_level_id === Number(gradeLevelId))
    .sort((a, b) => a.name.localeCompare(b.name)), [academicStructure.sections, gradeLevelId]);
  const missingStudentPlacement = !isExistingPerson && form.role === 'Student'
    && (!form.school_year_id || !form.enrollment_start_date || !form.grade || !form.section || !availableSections.some((section) => section.name === form.section));
  const patch = (field, value) => setForm((current) => ({ ...current, [field]: value, ...(field === 'role' && value !== current.role ? { enrollment_status: value === 'Student' ? 'Regular' : 'Appointed', enrollment_end_date: '', school_year_id: '' } : {}) }));

  const startCamera = async () => {
    const generation = cameraGeneration.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 960 }, height: { ideal: 720 } }, audio: false });
      if (generation !== cameraGeneration.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCameraOn(true);
    } catch (err) { showError(`Camera could not start: ${err.message}`); }
  };

  const captureDataset = async () => {
    setEnrollmentError(null);
    setFrames([]); setIsCapturing(true);
    const collected = [];
    try {
      for (let index = 0; index < targetFrames; index += 1) {
        collected.push(await captureVideoFrame(videoRef.current, enrollmentCapture.quality, enrollmentCapture.maxDimension));
        setFrames([...collected]);
        await new Promise((resolve) => window.setTimeout(resolve, enrollmentCapture.interval));
      }
      showSuccess(`${collected.length} live camera frames captured. The server will check face quality and duplicate enrollment before training.`);
    } catch (err) { showError(err.message); }
    finally { setIsCapturing(false); }
  };

  const saveAndTrain = async () => {
    if (!isExistingPerson && (!isValidPersonName(form.surname) || !isValidPersonName(form.first_name)
      || (form.middle_name && !isValidPersonName(form.middle_name))
      || (form.name_extension && !isValidPersonName(form.name_extension)))) {
      return showError('Enter names using letters and common name punctuation only. Numbers and other symbols are not allowed.');
    }
    if (!assistedRegistration && !(isExistingPerson ? person.biometric_consent : form.biometric_consent)) return showError('Confirm the documented consent/authorization before biometric enrollment.');
    if (!isExistingPerson && form.role === 'Student' && !form.lrn.trim()) return showError('Enter the student LRN.');
    if (!isExistingPerson && form.role === 'Student' && !form.date_of_birth) return showError('Enter the student’s date of birth.');
    if (!isExistingPerson && form.role !== 'Student' && !form.external_id.trim()) return showError('Enter the employee ID.');
    if (missingStudentPlacement) return showError('Choose the school year, active grade and section, and enrollment start date before enrolling this student.');
    if (isReplacement && changeReason.trim().length < 8) return showError('Enter a specific re-enrollment reason of at least 8 characters.');
    if (!assistedRegistration && frames.length < targetFrames) return showError(`Capture all ${targetFrames} camera frames first.`);
    setSaving(true);
    setEnrollmentError(null);
    try {
      const payload = { ...form, external_id: form.role === 'Student' ? form.lrn : form.external_id, lrn: form.role === 'Student' ? form.lrn || null : null, school_year_id: form.role === 'Student' ? Number(form.school_year_id) : null, date_of_birth: form.date_of_birth || null, guardian_phone: form.guardian_phone || null, enrollment_start_date: form.enrollment_start_date || null, enrollment_end_date: form.enrollment_end_date || null, transfer_school: form.transfer_school || null, enrollment_note: form.enrollment_note || null, grade: form.role === 'Student' ? form.grade : null, section: form.role === 'Student' ? form.section : null, assignment: form.role === 'Student' ? null : form.assignment || null };
      if (assistedRegistration) {
        const id = personId || (await api.post('/persons', payload)).id;
        setPersonId(id);
        showSuccess('School record saved without face samples or attendance. Use Attendance → Assist after verifying this person in person.');
        onSaved?.({ person_id: id, assisted_registration: true });
        return;
      }
      const multipart = new FormData();
      frames.forEach((frame, index) => multipart.append('frames', frame, `enrollment-${index + 1}.jpg`));
      multipart.append('reason', isReplacement ? changeReason.trim() : 'Initial facial enrollment at gate station');
      let result;
      if (!personId) {
        multipart.append('person', JSON.stringify(payload));
        result = await api.post('/biometrics/register', multipart);
        setPersonId(result.person_id);
      } else {
        result = isReplacement
          ? await api.put(`/biometrics/enrollments/${personId}`, multipart)
          : await api.post(`/biometrics/enrollments/${personId}`, multipart);
      }
      showSuccess(`${result.accepted} quality samples encrypted and saved. LBPH model ${result.model.version} trained for ${result.model.person_count} person(s). ${result.sms?.message || ''}`);
      window.setTimeout(() => onSaved?.(result), 1800);
    } catch (err) {
      const feedback = buildEnrollmentFeedback(err, isReplacement);
      if (!personId && !assistedRegistration) feedback.note = 'New school records are saved only after face enrollment succeeds.';
      setEnrollmentError(feedback);
      showError(feedback.message);
    }
    finally { setSaving(false); }
  };

  return (
    <div className="modal-backdrop"><div className="modal-card enrollment-modal">
      <div className="modal-header"><div><p className="eyebrow">{assistedRegistration ? 'School record' : 'Encrypted local dataset'}</p><h2><ScanFace size={24} /> {assistedRegistration ? 'Register for staff-assisted attendance' : isReplacement ? 'Replace facial enrollment' : isExistingPerson ? 'Enroll face for registered person' : 'Enroll person & train LBPH'}</h2></div><button onClick={onClose} className="icon-btn"><X size={22} /><span className="control-label">Close</span></button></div>
      <p className="section-copy">Enrollment saves face samples and trains the model. It does not record Time In or Time Out. Start gate recognition separately to record attendance.</p>
      {!isExistingPerson && <label className="checkbox-field"><input type="checkbox" checked={assistedRegistration} disabled={saving || isCapturing} onChange={(event) => {
        setAssistedRegistration(event.target.checked);
        cameraGeneration.current += 1;
        streamRef.current?.getTracks().forEach((track) => track.stop());
        setCameraOn(false);
        setFrames([]);
        setEnrollmentError(null);
      }} /><span>Register without face samples for staff-assisted attendance</span></label>}
      <div className="enrollment-content">
        {isExistingPerson ? <div className="enrollment-fields">
          <div className="enrollment-identity"><span>Authorized person</span><strong>{person.full_name}</strong><small>{person.external_id} · {person.role}{person.grade ? ` · Grade ${person.grade} — ${person.section}` : ''}</small></div>
          <div className="notice notice-warning"><AlertTriangle size={18} /><span>{isReplacement ? 'The current encrypted samples will be securely replaced after the new dataset passes quality checks. The audit history remains.' : 'This face enrollment will use the existing school record. Capture this person’s own face after confirming their documented consent.'}</span></div>
          {isReplacement && <label><span className="field-label">Required re-enrollment reason</span><textarea className="text-area" placeholder="Example: Appearance changed and recognition accuracy was verified as poor" value={changeReason} onChange={(event) => setChangeReason(event.target.value)} /></label>}
        </div> : <div className="form-grid two-columns enrollment-fields">
          {form.role === 'Student'
            ? <label><span className="field-label">LRN</span><input placeholder="e.g. 123456789012" className="input-field" value={form.lrn} onChange={(e) => patch('lrn', e.target.value)} required /></label>
            : <label><span className="field-label">Employee ID</span><input placeholder="e.g. EMP-001" className="input-field" value={form.external_id} onChange={(e) => patch('external_id', e.target.value)} required /></label>}
          <label><span className="field-label">Role</span><select className="input-field" value={form.role} onChange={(e) => patch('role', e.target.value)}><option>Student</option><option>Faculty</option><option>Non-teaching Personnel</option></select></label>
          <label><span className="field-label">Last name</span><input placeholder="e.g. Dela Cruz" className="input-field" pattern={personNamePattern} title="Use letters and common name punctuation only." value={form.surname} onChange={(e) => patch('surname', e.target.value)} required /></label>
          <label><span className="field-label">First name</span><input placeholder="e.g. Juan" className="input-field" pattern={personNamePattern} title="Use letters and common name punctuation only." value={form.first_name} onChange={(e) => patch('first_name', e.target.value)} required /></label>
          <label><span className="field-label">Middle name</span><input placeholder="Middle name, if applicable" className="input-field" pattern={personNamePattern} title="Use letters and common name punctuation only." value={form.middle_name} onChange={(e) => patch('middle_name', e.target.value)} /></label>
          <label><span className="field-label">Extension (e.g., Jr.)</span><input placeholder="e.g. Jr. (leave blank if none)" className="input-field" pattern={personNamePattern} title="Use letters and common name punctuation only." value={form.name_extension} onChange={(e) => patch('name_extension', e.target.value)} /></label>
          <label><span className="field-label">Sex for official roster</span><select className="input-field" value={form.sex} onChange={(e) => patch('sex', e.target.value)}><option>Male</option><option>Female</option></select></label>
          {form.role === 'Student' ? <><label><span className="field-label">School year</span><select className="input-field" value={form.school_year_id} disabled={academicLoading || Boolean(academicError)} onChange={(e) => patch('school_year_id', e.target.value)} required><option value="">Select a school year</option>{(academicStructure.school_years || []).map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label><label><span className="field-label">Grade</span><select className="input-field" value={gradeLevelId} disabled={academicLoading || Boolean(academicError)} onChange={(e) => {
            const value = e.target.value;
            const grade = sortedGrades.find((item) => item.id === Number(value));
            setGradeLevelId(value);
            patch('grade', grade?.name || '');
            patch('section', '');
          }} required><option value="">{academicLoading ? 'Loading grades…' : 'Select a grade'}</option>{sortedGrades.map((grade) => <option key={grade.id} value={grade.id}>Grade {normalizeGradeName(grade.name)}</option>)}</select></label><label><span className="field-label">Section</span><select className="input-field" value={form.section} disabled={!gradeLevelId || academicLoading || Boolean(academicError)} onChange={(e) => patch('section', e.target.value)} required><option value="">Select a section</option>{availableSections.map((section) => <option key={section.id} value={section.name}>{section.name}</option>)}</select></label><PhoneNumberField label="Parent/guardian mobile number" value={form.guardian_phone} onChange={value => patch('guardian_phone', value)} />
            {academicError && <div className="notice notice-danger full-field" role="alert"><AlertTriangle size={18} /><span>Could not load grade and section records: {academicError}</span></div>}
            {!academicLoading && !academicError && sortedGrades.length === 0 && <div className="notice notice-warning full-field" role="status">Add an active grade level and section in Administration before enrolling a student.</div>}
          </>
            : <><label className="full-field"><span className="field-label">Office / assignment</span><input placeholder="e.g. Science department (blank for role default)" className="input-field" value={form.assignment} onChange={(e) => patch('assignment', e.target.value)} /></label><PhoneNumberField label="Phone number" value={form.guardian_phone} onChange={value => patch('guardian_phone', value)} /></>}
          <EnrollmentFields form={form} onChange={patch} dateOfBirthRequired={!isExistingPerson} enrollmentStartDateRequired={!isExistingPerson} />
          <BiometricConsent checked={form.biometric_consent} onChange={(value) => patch('biometric_consent', value)} />
        </div>}
        <div className="enrollment-camera">
          {assistedRegistration ? <div className="notice notice-blue"><div><strong>Camera-free registration</strong><p>For anyone who cannot complete face capture or blinking, including people with facial differences. Save their school record here, then use Attendance → Assist to verify their school ID or roster and record an attended visit. No face samples, medical details, or attendance are saved by this option.</p></div></div> : <>
          <div className="enrollment-video"><video ref={videoRef} playsInline muted />{!cameraOn && <><Camera size={48} /><span className="camera-placeholder-label">Camera is off</span></>}{isCapturing && <div className="capture-indicator">CAPTURING</div>}{frames.length === targetFrames && !isCapturing && <><CheckCircle className="capture-complete" size={48} /><span className="capture-complete">Captured</span></>}</div>
          <div><div className="scan-log-top"><strong>Camera frames</strong><span>{frames.length}/{targetFrames}</span></div><div className="weight-meter weight-valid"><span style={{ width: `${frames.length / targetFrames * 100}%` }} /></div><p className="muted-small">Human faces only. Keep one person in view with both eyes, nose, and mouth visible. Capture this person's own face; each face belongs to one enrolled identity. Face forward and move slowly while frames are captured.</p></div>
          {enrollmentError && <div className="notice notice-warning" role="alert"><AlertTriangle size={18} /><div><strong>{enrollmentError.title}</strong><p>{enrollmentError.message}</p><p className="muted-small">{enrollmentError.note}</p>{enrollmentError.reasons.length > 0 && <details><summary>Capture details</summary><ul>{enrollmentError.reasons.slice(0, 3).map(reason => <li key={reason}>{reason}</li>)}</ul></details>}</div></div>}
          {!cameraOn ? <button className="btn-primary" onClick={startCamera}><Camera size={16} /> Enable camera</button> : <button className="btn-secondary" onClick={captureDataset} disabled={isCapturing || saving}>{isCapturing ? 'Capturing real frames…' : 'Capture enrollment frames'}</button>}
          <p className="muted-small">Unable to complete camera verification? Authorized staff can use <a href="/dashboard/attendance">Attendance → Assist</a> after checking the person's school ID or official roster. No medical details are needed.</p>
          </>}
        </div>
      </div>
      <div className="modal-actions"><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={saveAndTrain} disabled={saving || isCapturing || (!assistedRegistration && frames.length < targetFrames) || missingStudentPlacement || (form.role === 'Student' && (academicLoading || Boolean(academicError)))}><Database size={16} /> {saving ? assistedRegistration ? 'Saving school record…' : 'Checking quality & duplicate faces…' : assistedRegistration ? 'Save school record only' : isReplacement ? 'Replace samples & retrain model' : 'Save encrypted samples & train model'}</button></div>
    </div></div>
  );
}
