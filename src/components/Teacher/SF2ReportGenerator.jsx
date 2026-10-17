import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ChevronDown, Download, FileSpreadsheet, Upload } from 'lucide-react';
import { api, auth, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function SF2ReportGenerator() {
  const [month, setMonth] = useState(localDate().slice(0, 7));
  const [grade, setGrade] = useState('');
  const [section, setSection] = useState('');
  const [availableSections, setAvailableSections] = useState([]);
  const [schoolId, setSchoolId] = useState('');
  const [schoolYear, setSchoolYear] = useState('2026-2027');
  const [students, setStudents] = useState([]);
  const [todayRows, setTodayRows] = useState([]);
  const [template, setTemplate] = useState({ configured: false });
  const { showSuccess, showError } = useToast();

  useEffect(() => {
    Promise.all([api.get('/my/advisory-sections'), api.get('/sf2/template')]).then(([sections, status]) => {
      setAvailableSections(sections); setTemplate(status);
      if (sections.length) { setGrade(sections[0].grade); setSection(sections[0].section); }
    }).catch((err) => showError(err.message));
  }, [showError]);

  const load = useCallback(() => {
    if (!grade || !section) return;
    const query = `grade=${encodeURIComponent(grade)}&section=${encodeURIComponent(section)}`;
    return Promise.all([api.get(`/persons?role=Student&${query}`), api.get(`/attendance?date=${localDate()}&${query}`)])
      .then(([people, attendance]) => { setStudents(people); setTodayRows(attendance); })
      .catch((err) => showError(err.message));
  }, [grade, section, showError]);
  useEffect(() => { load(); }, [load]);

  const male = students.filter((student) => student.sex === 'Male').length;
  const female = students.filter((student) => student.sex === 'Female').length;
  const overflow = male > 21 || female > 25;
  const sectionKey = `${grade}|${section}`;

  const chooseSection = (value) => {
    const item = availableSections.find((row) => `${row.grade}|${row.section}` === value);
    if (item) { setGrade(item.grade); setSection(item.section); }
  };
  const upload = async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    const form = new FormData(); form.append('file', file);
    try { await api.post('/sf2/template', form); setTemplate({ configured: true, filename: file.name }); showSuccess('Official SF2 template uploaded and validated.'); }
    catch (err) { showError(err.message); }
  };
  const downloadTemporaryLog = () => {
    const query = new URLSearchParams({ date: localDate(), grade, section });
    api.download(`/attendance/temporary-log?${query}`, `attendance-${localDate()}-Grade-${grade}-${section}.xlsx`).catch((err) => showError(err.message));
  };
  const exportFile = async () => {
    const [year, monthNumber] = month.split('-').map(Number);
    const query = new URLSearchParams({ year, month: monthNumber, grade, section, school_id: schoolId, school_year: schoolYear, school_name: 'SAN JOSE NATIONAL HIGH SCHOOL' });
    try { await api.download(`/sf2/export?${query}`, `SF2-${month}-${grade}-${section}.xlsx`); showSuccess('SF2 workbook generated. The records officer must verify it before submission.'); }
    catch (err) { showError(err.message); }
  };

  return <div className="page-stack">
    <section className="card-static">
      <div className="section-heading"><div><p className="eyebrow">Official XLSX generation</p><h2>SF2 monthly attendance report</h2><p className="section-copy">Select one adviser section. Learners are deduplicated by ID/LRN, alphabetized within the male/female blocks, and transfer remarks are written into the official remarks field.</p></div><FileSpreadsheet size={28} /></div>
      {availableSections.length === 0 && <div className="notice notice-warning">No active section is available. Administrators must create a grade/section and assign an adviser account before teachers can export records.</div>}
      <div className="form-grid three-columns">
        <label><span className="field-label">Reporting month</span><input className="input-field" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>
        <label><span className="field-label">Adviser section</span><select className="input-field" value={sectionKey} onChange={(event) => chooseSection(event.target.value)}>{availableSections.map((item) => <option key={item.id} value={`${item.grade}|${item.section}`}>Grade {item.grade} — {item.section}{item.adviser_name ? ` · ${item.adviser_name}` : ''}</option>)}</select></label>
        <label><span className="field-label">School year</span><input className="input-field" value={schoolYear} onChange={(event) => setSchoolYear(event.target.value)} /></label>
        <label><span className="field-label">School ID</span><input className="input-field" value={schoolId} onChange={(event) => setSchoolId(event.target.value)} /></label>
      </div>
      <div className="report-action-bar"><div><strong>{students.length} learner(s)</strong><span>{male} male · {female} female · {template.configured ? template.filename : 'Template missing'}</span></div><div className="action-row"><details className="action-menu"><summary><ChevronDown size={16} /> Supporting files</summary><div className="action-menu-panel">{auth.role() === 'admin' && <label><Upload size={16} /> {template.configured ? 'Replace official template' : 'Upload official template'}<input type="file" accept=".xlsx" onChange={upload} hidden /></label>}<button onClick={downloadTemporaryLog}><Download size={16} /> Download section log</button></div></details><button className="btn-primary" disabled={overflow || !template.configured || !month || !grade || !section} onClick={exportFile}><Download size={17} /> Generate official SF2</button></div></div>
      {overflow && <div className="notice notice-danger"><AlertTriangle size={18} /> Template capacity exceeded: {male}/21 male and {female}/25 female learners. Resolve the roster before export.</div>}
    </section>
    <section className="card-static"><h2>Current-day placement preview</h2><p className="section-copy">Transferred learners remain in alphabetical order and receive a movement remark. “No scan” remains pending until authorized daily close or correction.</p><div className="table-scroll"><table className="interactive-table"><thead><tr><th>SF2 row</th><th>Learner</th><th>ID / LRN</th><th>Sex block</th><th>Movement</th><th>Today</th><th>Template mark</th></tr></thead><tbody>{todayRows.map((student) => { const block = todayRows.filter((item) => item.sex === student.sex).sort((a, b) => a.full_name.localeCompare(b.full_name)); const row = (student.sex === 'Male' ? 14 : 36) + block.findIndex((item) => item.person_id === student.person_id); const mark = student.status === 'Absent' ? 'X' : student.status === 'Late' ? 'Upper-half shade' : ['Present', 'Time Out'].includes(student.status) ? 'Blank (present)' : student.status; return <tr key={student.person_id}><td><strong>{row}</strong></td><td>{student.full_name}</td><td>{student.external_id}{student.lrn ? ` / ${student.lrn}` : ''}</td><td>{student.sex}</td><td>{student.enrollment_status}{student.transfer_school ? <span className="table-subline">{student.transfer_school}</span> : null}</td><td>{student.status}</td><td>{mark}</td></tr>; })}</tbody></table></div></section>
  </div>;
}
