import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useState } from 'react';
import { Download, FileClock, FileSpreadsheet, Printer } from 'lucide-react';
import SF2ReportGenerator from '../../components/Teacher/SF2ReportGenerator';
import ReleasedSF2Reports from '../../components/Teacher/ReleasedSF2Reports';
import MySchedules from '../Teacher/MySchedules';
import { api, auth, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function Reports() {
  return auth.role() === 'teacher' ? <div className="page-stack"><MySchedules /><ReleasedSF2Reports /></div> : <AdminReports />;
}

function AdminReports() {
  const today = localDate();
  const [startsOn, setStartsOn] = useState(today);
  const [endsOn, setEndsOn] = useState(today);
  const [daily, setDaily] = useState(true);
  const [dailyRows, setDailyRows] = useState([]);
  const [dailyContext, setDailyContext] = useState('');
  const [role, setRole] = useState('Student');
  const [{ grade, section }, setSelection] = useState({ grade: '', section: '' });
  const [sections, setSections] = useState([]);
  const [history, setHistory] = useState([]);
  const [review, setReview] = useState({});
  const { showSuccess, showError } = useToast();
  const canGenerate = auth.role() === 'admin';

  const load = useCallback(() => api.get('/reports/history')
    .then(setHistory).catch((err) => showError(err.message)), [showError]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!canGenerate) return undefined;
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
  }, [startsOn, endsOn, showError, canGenerate]);

  useEffect(() => {
    if (!canGenerate || !daily || !startsOn) return undefined;
    let cancelled = false;
    const query = new URLSearchParams({ date: startsOn });
    if (role === 'Student' && grade && section) { query.set('grade', grade); query.set('section', section); }
    api.get(`/attendance?${query}`).then(rows => { if (!cancelled) { setDailyRows(role ? rows.filter(row => row.role === role) : rows); setDailyContext(`${startsOn}|${role}|${grade}|${section}`); } }).catch(error => { if (!cancelled) showError(error.message); });
    return () => { cancelled = true; };
  }, [canGenerate, daily, startsOn, role, grade, section, showError]);

  const query = () => {
    const value = new URLSearchParams({ starts_on: startsOn, ends_on: daily ? startsOn : endsOn });
    if (role) value.set('role', role);
    if ((role === 'Student') && grade && section) { value.set('grade', grade); value.set('section', section); }
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

    {canGenerate && <><section className="card-static">
      <div className="section-heading"><div><p className="eyebrow">Selected reporting period</p><h2>{daily ? 'Daily attendance and movement summary' : 'Attendance and movement summary'}</h2></div><FileSpreadsheet size={24} /></div>
      <div className="form-grid three-columns">
        <label><span className="field-label">Report period</span><select className="input-field" value={daily ? 'daily' : 'range'} onChange={event => setDaily(event.target.value === 'daily')}><option value="daily">Daily attendance</option><option value="range">Date range</option></select></label>
        <label><span className="field-label">{daily ? 'Attendance date' : 'From'}</span><input title="Choose a calendar date" className="input-field" type="date" value={startsOn} onChange={(event) => setStartsOn(event.target.value)} /></label>
        {!daily && <label><span className="field-label">To</span><input title="Choose a calendar date" className="input-field" type="date" min={startsOn} value={endsOn} onChange={(event) => setEndsOn(event.target.value)} /></label>}
        <label><span className="field-label">Population</span><select className="input-field" value={role} onChange={(event) => setRole(event.target.value)}><option value="">School-wide</option><option>Student</option><option>Faculty</option><option>Non-teaching Personnel</option></select></label>
        {(role === 'Student') && <label><span className="field-label">Section</span><select className="input-field" value={`${grade}|${section}`} onChange={(event) => chooseSection(event.target.value)}><option value="|">All authorized sections</option>{sections.map((item) => <option key={item.id} value={`${item.grade}|${item.section}`}>Grade {item.grade} — {item.section}</option>)}</select></label>}
      </div>
      <p className="section-copy">Daily output uses the selected attendance date. No scan remains pending until daily close. Departures show their recorded reason; use the separate SF2 below for the monthly learner report. Every registered XLSX includes generation metadata and a SHA-256 integrity hash.</p>
      {daily && <><p className="muted-small">{dailyContext === `${startsOn}|${role}|${grade}|${section}` ? dailyRows.length : 'Loading'} record(s) on {startsOn}. This preview does not create or close attendance.</p><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Name</th><th>Role / class</th><th>Daily attendance</th><th>Enrollment / employment</th></tr></thead><PaginatedBody resetKey={dailyContext}>{(dailyContext === `${startsOn}|${role}|${grade}|${section}` ? dailyRows : []).map(row => <tr key={row.person_id}><td>{row.full_name}</td><td>{row.role}{row.grade ? ` - Grade ${row.grade}, ${row.section}` : ''}</td><td>{row.status}</td><td>{row.enrollment_status}</td></tr>)}</PaginatedBody></table></div></>}
      <div className="action-row"><button className="btn-primary" disabled={!startsOn || (!daily && (!endsOn || endsOn < startsOn))} onClick={() => api.download(`/attendance/report.xlsx?${query()}`, 'attendance-report.xlsx').then(load).catch((err) => showError(err.message))}><Download size={16} /> Export XLSX</button><button className="btn-secondary" disabled={!startsOn || (!daily && (!endsOn || endsOn < startsOn))} onClick={() => api.printHtml(`/attendance/report/print?${query()}`).catch((err) => showError(err.message))}><Printer size={16} /> Printable report</button></div>
    </section>
    <SF2ReportGenerator /></>}
    <section className="card-static">
      <div className="section-heading"><div><p className="eyebrow">Attributable report generation</p><h2>Generated-report history</h2></div><FileClock size={24} /></div>
      <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Generated</th><th>Type / file</th><th>Parameters</th><th>Hash</th><th>Status</th><th>Review</th></tr></thead><PaginatedBody>{history.length === 0 && <tr><td colSpan="6" className="empty-cell">No registered reports yet.</td></tr>}{history.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}<span className="table-subline">{item.generated_by_name}</span></td><td><strong>{item.report_type}</strong><button className="btn-link" onClick={() => api.download(`/reports/history/${item.id}/download`, item.filename)}><Download size={14} /> {item.filename}</button></td><td>{Object.entries(item.parameters || {}).map(([key, value]) => <span className="table-subline" key={key}>{key}: {String(value || '—')}</span>)}</td><td title={item.sha256}>{item.sha256.slice(0, 12)}…</td><td><span className="tag tag-gray">{item.status}</span>{item.reviewed_by_name && <span className="table-subline">{item.reviewed_by_name}</span>}</td><td>{['admin', 'records_officer'].includes(auth.role()) ? <div><input className="input-field" placeholder="Review note" value={review[item.id] || ''} onChange={(event) => setReview((current) => ({ ...current, [item.id]: event.target.value }))} /><details className="action-menu"><summary>Set status</summary><div className="action-menu-panel">{['Reviewed', 'Approved', 'Rejected', 'Superseded'].map((status) => <button key={status} onClick={() => markReport(item, status)}>{status}</button>)}</div></details></div> : (item.review_note || 'Awaiting records review')}</td></tr>)}</PaginatedBody></table></div>
    </section>
  </div>;
}
