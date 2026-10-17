import { useCallback, useEffect, useState } from 'react';
import { Download, FileClock, FileSpreadsheet, Printer } from 'lucide-react';
import SF2ReportGenerator from '../../components/Teacher/SF2ReportGenerator';
import { api, auth, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function Reports() {
  const today = localDate();
  const [startsOn, setStartsOn] = useState(`${today.slice(0, 8)}01`);
  const [endsOn, setEndsOn] = useState(today);
  const [role, setRole] = useState('Student');
  const [{ grade, section }, setSelection] = useState({ grade: '', section: '' });
  const [sections, setSections] = useState([]);
  const [history, setHistory] = useState([]);
  const [review, setReview] = useState({});
  const { showSuccess, showError } = useToast();
  const isTeacher = String(auth.role()).toLowerCase() === 'teacher';
  const isSchoolHead = auth.role() === 'school_head';

  const load = useCallback(() => api.get('/reports/history')
    .then(setHistory).catch((err) => showError(err.message)), [showError]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (isSchoolHead) return undefined;
    let cancelled = false;
    const period = new URLSearchParams({ starts_on: startsOn, ends_on: endsOn });
    api.get(`/my/report-sections?${period}`)
      .then((available) => {
        if (cancelled) return;
        setSections(available);
        setSelection((current) => available.some((item) => item.grade === current.grade && item.section === current.section)
          ? current
          : available[0] ? { grade: available[0].grade, section: available[0].section } : { grade: '', section: '' });
      })
      .catch((err) => { if (!cancelled) showError(err.message); });
    return () => { cancelled = true; };
  }, [startsOn, endsOn, showError, isSchoolHead]);

  const query = () => {
    const value = new URLSearchParams({ starts_on: startsOn, ends_on: endsOn });
    if (role) value.set('role', role);
    if ((isTeacher || role === 'Student') && grade && section) { value.set('grade', grade); value.set('section', section); }
    return value;
  };
  const chooseSection = (value) => {
    const selected = sections.find((item) => `${item.grade}|${item.section}` === value);
    setSelection(selected ? { grade: selected.grade, section: selected.section } : { grade: '', section: '' });
  };
  const markReport = async (item, status) => {
    try {
      await api.post(`/reports/history/${item.id}/review`, { status, note: review[item.id] || `Records review: ${status}` });
      showSuccess(`Report marked ${status}.`); await load();
    } catch (err) { showError(err.message); }
  };

  return <div className="page-stack">

    {!isSchoolHead && <><section className="card-static">
      <div className="section-heading"><div><p className="eyebrow">Selected reporting period</p><h2>Attendance and movement summary</h2></div><FileSpreadsheet size={24} /></div>
      <div className="form-grid three-columns">
        <label><span className="field-label">From</span><input className="input-field" type="date" value={startsOn} onChange={(event) => setStartsOn(event.target.value)} /></label>
        <label><span className="field-label">To</span><input className="input-field" type="date" value={endsOn} onChange={(event) => setEndsOn(event.target.value)} /></label>
        <label><span className="field-label">Population</span><select className="input-field" value={isTeacher ? 'Student' : role} disabled={isTeacher} onChange={(event) => setRole(event.target.value)}>{isTeacher ? <option>Student</option> : <><option value="">School-wide</option><option>Student</option><option>Faculty</option><option>Non-teaching Personnel</option></>}</select></label>
        {(isTeacher || role === 'Student') && <label><span className="field-label">Section</span><select className="input-field" value={`${grade}|${section}`} onChange={(event) => chooseSection(event.target.value)}><option value="|">{isTeacher ? 'Select an assigned section' : 'All authorized sections'}</option>{sections.map((item) => <option key={item.id} value={`${item.grade}|${item.section}`}>Grade {item.grade} — {item.section}</option>)}</select></label>}
      </div>
      {isTeacher && sections.length === 0 && <div className="notice notice-warning">No sections are assigned to you during this reporting period.</div>}
      <p className="section-copy">{isTeacher ? 'Teacher reports are limited to student attendance in sections assigned during the selected date range.' : 'Faculty and non-teaching selections produce monthly personnel attendance output for the same range.'} Every registered XLSX includes generation metadata and a SHA-256 integrity hash.</p>
      <div className="action-row"><button className="btn-primary" disabled={isTeacher && (!grade || !section || !sections.some((item) => item.grade === grade && item.section === section))} onClick={() => api.download(`/attendance/report.xlsx?${query()}`, 'attendance-report.xlsx').then(load).catch((err) => showError(err.message))}><Download size={16} /> Export XLSX</button><button className="btn-secondary" disabled={isTeacher && (!grade || !section || !sections.some((item) => item.grade === grade && item.section === section))} onClick={() => api.printHtml(`/attendance/report/print?${query()}`).catch((err) => showError(err.message))}><Printer size={16} /> Printable report</button></div>
    </section>
    <SF2ReportGenerator /></>}
    <section className="card-static">
      <div className="section-heading"><div><p className="eyebrow">Attributable report generation</p><h2>Generated-report history</h2></div><FileClock size={24} /></div>
      <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Generated</th><th>Type / file</th><th>Parameters</th><th>Hash</th><th>Status</th><th>Review</th></tr></thead><tbody>{history.length === 0 && <tr><td colSpan="6" className="empty-cell">No registered reports yet.</td></tr>}{history.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}<span className="table-subline">{item.generated_by_name}</span></td><td><strong>{item.report_type}</strong><button className="btn-link" onClick={() => api.download(`/reports/history/${item.id}/download`, item.filename)}><Download size={14} /> {item.filename}</button></td><td>{Object.entries(item.parameters || {}).map(([key, value]) => <span className="table-subline" key={key}>{key}: {String(value || '—')}</span>)}</td><td title={item.sha256}>{item.sha256.slice(0, 12)}…</td><td><span className="tag tag-gray">{item.status}</span>{item.reviewed_by_name && <span className="table-subline">{item.reviewed_by_name}</span>}</td><td>{['admin', 'records_officer'].includes(auth.role()) ? <div><input className="input-field" placeholder="Review note" value={review[item.id] || ''} onChange={(event) => setReview((current) => ({ ...current, [item.id]: event.target.value }))} /><details className="action-menu"><summary>Set status</summary><div className="action-menu-panel">{['Reviewed', 'Approved', 'Rejected', 'Superseded'].map((status) => <button key={status} onClick={() => markReport(item, status)}>{status}</button>)}</div></details></div> : (item.review_note || 'Awaiting records review')}</td></tr>)}</tbody></table></div>
    </section>
  </div>;
}
