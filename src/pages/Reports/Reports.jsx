import SavedReportActions from '../../components/Reports/SavedReportActions';
import ActionMenu from '../../components/Common/ActionMenu';
import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import SF2ReportGenerator from '../../components/Teacher/SF2ReportGenerator';
import ReleasedSF2Reports, { OfficialSF2Preview } from '../../components/Teacher/ReleasedSF2Reports';
import Modal from '../../components/Common/Modal';
import AnnexGWorkspace from '../../components/Reports/AnnexGWorkspace';
import MonthlyDtr from '../../components/Reports/MonthlyDtr';
import { api, auth, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import './Reports.css';

export default function Reports() {
  return auth.role() === 'teacher' ? <div className="page-stack reports-page"><header className="reports-heading"><h1>Reports</h1><p>Prepare learner reports and review official SF2 reports for your assigned classes.</p></header><ReportNavigation teacher /><div id="learner-reports" className="reports-workspace"><AnnexGWorkspace /></div><DeferredReport id="released-sf2" title="Official SF2 reports"><ReleasedSF2Reports /></DeferredReport></div> : <AdminReports />;
}

function DeferredReport({ id, title, children }) {
  const element = useRef(null);
  const { hash } = useLocation();
  const active = hash === `#${id}`;
  const [loaded, setLoaded] = useState(active);
  useEffect(() => {
    if (active) { setLoaded(true); return undefined; }
    if (loaded) return undefined;
    const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) setLoaded(true);
    });
    if (observer) observer.observe(element.current);
    else setLoaded(true);
    return () => observer?.disconnect();
  }, [active, loaded]);
  return <div ref={element} id={id} className="reports-workspace">{loaded || active ? children :
    <section className="card-static"><h2>{title}</h2><p className="section-copy">Loads when you reach this section.</p>
      <button type="button" className="btn-secondary" onClick={() => setLoaded(true)}>Load {title}</button></section>}
  </div>;
}

function ReportNavigation({ teacher = false, canGenerate = false }) {
  const { pathname, search, hash, state, key } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' });
  }, [hash, key]);
  const links = teacher ? [
    ['learner-reports', 'Annex G learner reports'],
    ['released-sf2', 'Official SF2 reports'],
  ] : [
    ...(canGenerate ? [['daily-reports', 'Daily attendance'], ['monthly-dtr', 'Monthly DTR'], ['monthly-sf2', 'Monthly SF2']] : []),
    ['report-history', 'Report history'],
    ['learner-reports', 'Annex G learner reports'],
  ];
  const current = links.find(([id]) => `#${id}` === hash)?.[0] || links[0][0];
  return <nav className="reports-navigation" aria-label="Report workspaces">
    {links.map(([id, label]) => <Link key={id} to={{ pathname, search, hash: `#${id}` }} state={state}
      replace={hash === `#${id}`} aria-current={current === id ? 'location' : undefined}>
      <span>{label}</span>
    </Link>)}
  </nav>;
}

function AdminReports() {
  const { search, state } = useLocation();
  const selectedReport = new URLSearchParams(search).get('report');
  const today = localDate();
  const [startsOn, setStartsOn] = useState(today);
  const [endsOn, setEndsOn] = useState(today);
  const [daily, setDaily] = useState(true);
  const [dailyRows, setDailyRows] = useState([]);
  const [dailyContext, setDailyContext] = useState('');
  const [dailyError, setDailyError] = useState({ context: '', message: '' });
  const [role, setRole] = useState('Student');
  const [dtrRole, setDtrRole] = useState('Faculty');
  const [{ grade, section }, setSelection] = useState({ grade: '', section: '' });
  const [sections, setSections] = useState([]);
  const [history, setHistory] = useState([]);
  const historyRequest = useRef(0);
  const [sf2Preview, setSF2Preview] = useState(null);
  const [historyState, setHistoryState] = useState({ loading: true, error: '' });
  const [review, setReview] = useState({});
  const { showSuccess, showError } = useToast();
  const canGenerate = auth.role() === 'admin';
  const personnel = role === 'Faculty' || role === 'Non-teaching Personnel';

  const load = useCallback(() => {
    const request = ++historyRequest.current;
    setHistoryState({ loading: true, error: '' });
    const query = selectedReport ? '?' + new URLSearchParams({ report_id: selectedReport }) : '';
    return api.get('/reports/history' + query).then((items) => {
      if (request !== historyRequest.current) return;
      setHistory(items);
      setHistoryState({ loading: false, error: '' });
    }).catch((err) => {
      if (request !== historyRequest.current) return;
      setHistoryState({ loading: false, error: err.message });
      showError(err.message);
    });
  }, [selectedReport, showError]);
  useEffect(() => {
    setHistory([]);
    load();
    return () => { historyRequest.current += 1; };
  }, [load]);

  useEffect(() => {
    if (!canGenerate) return undefined;
    let cancelled = false;
    const period = new URLSearchParams({ starts_on: startsOn, ends_on: daily ? startsOn : endsOn });
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
  }, [startsOn, endsOn, daily, showError, canGenerate]);

  useEffect(() => {
    if (!canGenerate || !daily || !startsOn) return undefined;
    let cancelled = false;
    const query = new URLSearchParams({ date: startsOn });
    if (role === 'Student' && grade && section) { query.set('grade', grade); query.set('section', section); }
    api.get(`/attendance?${query}`).then(rows => { if (!cancelled) { setDailyError({ context: '', message: '' }); setDailyRows(role ? rows.filter(row => row.role === role) : rows); setDailyContext(`${startsOn}|${role}|${grade}|${section}`); } }).catch(error => { if (!cancelled) { setDailyError({ context: `${startsOn}|${role}|${grade}|${section}`, message: error.message }); showError(error.message); } });
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

  const previewKey = `${startsOn}|${role}|${grade}|${section}`;
  const previewReady = dailyContext === previewKey;
  const previewError = dailyError.context === previewKey ? dailyError.message : '';
  const exportDisabled = !startsOn || (!daily && (!endsOn || endsOn < startsOn));
  const downloadAttendanceReport = (format) => api.download(`/attendance/report.${format}?${query()}`, `attendance-report.${format}`)
    .then(load)
    .catch((err) => showError(err.message));

  return <div className="page-stack reports-page">
    <header className="reports-heading"><h1>Reports</h1><p>Generate attendance reports, review saved files, and prepare learner reports.</p></header>
    <ReportNavigation canGenerate={canGenerate} />

    {canGenerate && <><section id="daily-reports" className="card-static reports-workspace reports-attendance">
      <div className="section-heading"><div><h2>{daily ? 'Daily attendance and movement summary' : 'Attendance and movement summary'}</h2></div></div>
      <div className="form-grid three-columns">
        <label><span className="field-label">Report period</span><select className="input-field" value={daily ? 'daily' : 'range'} onChange={event => setDaily(event.target.value === 'daily')}><option value="daily">Daily attendance</option><option value="range">Date range</option></select></label>
        <label><span className="field-label">{daily ? 'Attendance date' : 'From'}</span><input title="Choose a calendar date" className="input-field" type="date" value={startsOn} onChange={(event) => setStartsOn(event.target.value)} /></label>
        {!daily && <label><span className="field-label">To</span><input title="Choose a calendar date" className="input-field" type="date" min={startsOn} value={endsOn} onChange={(event) => setEndsOn(event.target.value)} /></label>}
        <label><span className="field-label">Population</span><select className="input-field" value={role} onChange={(event) => setRole(event.target.value)}><option value="">School-wide</option><option>Student</option><option>Faculty</option><option>Non-teaching Personnel</option></select></label>
        {(role === 'Student') && <label><span className="field-label">Section</span><select className="input-field" value={`${grade}|${section}`} onChange={(event) => chooseSection(event.target.value)}><option value="|">All authorized sections</option>{sections.map((item) => <option key={item.id} value={`${item.grade}|${item.section}`}>Grade {item.grade} — {item.section}</option>)}</select></label>}
      </div>
      <p className="section-copy">Daily output uses the selected attendance date. No scan remains pending until daily close. Departures show their recorded reason. Use the separate SF2 below for the monthly learner report. Every registered file includes generation metadata and a SHA-256 integrity hash.</p>
      {daily && <><div className="reports-preview-heading"><h3>Attendance preview</h3><p className="muted-small" role="status">{previewError ? `Preview unavailable: ${previewError}` : previewReady ? `${dailyRows.length} record(s) on ${startsOn}. This preview does not create or close attendance.` : 'Loading attendance preview…'}</p></div><div className="table-scroll"><table className="interactive-table reports-preview-table" aria-label="Daily attendance report preview"><thead><tr><th>Name</th><th>Role / class</th><th>Daily attendance</th><th>Enrollment / employment</th></tr></thead><PaginatedBody pageSize={5} resetKey={dailyContext} columnCount={4}>{(!previewReady || dailyRows.length === 0) && <tr><td colSpan="4" className="empty-cell">{previewError ? 'The preview could not be loaded for this selection.' : !previewReady ? 'Loading attendance records…' : 'No attendance records for this selection.'}</td></tr>}{(dailyContext === `${startsOn}|${role}|${grade}|${section}` ? dailyRows : []).map(row => <tr key={row.person_id}><td>{row.full_name}</td><td>{row.role}{row.grade ? ` - Grade ${row.grade}, ${row.section}` : ''}</td><td>{row.status}</td><td>{row.enrollment_status}</td></tr>)}</PaginatedBody></table></div></>}
      <div className="action-row">
        {personnel ? <a className="btn-primary" href="#monthly-dtr" onClick={() => setDtrRole(role)}>Open Monthly DTR</a> :
          <ActionMenu label="Export" disabled={exportDisabled}>
            <button type="button" onClick={() => downloadAttendanceReport('pdf')}>Download PDF</button>
            <button type="button" onClick={() => downloadAttendanceReport('xlsx')}>Download Excel (.xlsx)</button>
            <button type="button" onClick={() => api.openDocument(`/attendance/report/print?${query()}`).catch(err => showError(err.message))}>Print</button>
          </ActionMenu>}
      </div>
    </section>
    <DeferredReport id="monthly-dtr" title="Monthly DTR">
      <section className="card-static">
        <div className="section-heading"><div><h2>Monthly DTR (Form 48)</h2></div></div>
        <div className="form-grid three-columns">
          <label><span className="field-label">Personnel role</span><select className="input-field" value={dtrRole} onChange={event => setDtrRole(event.target.value)}><option>Faculty</option><option>Non-teaching Personnel</option></select></label>
        </div>
        <MonthlyDtr key={dtrRole} role={dtrRole} onDownload={load} />
      </section>
    </DeferredReport>
    <DeferredReport id="monthly-sf2" title="Monthly SF2"><div className="reports-sf2"><SF2ReportGenerator /></div></DeferredReport></>}
    <section id="report-history" className="card-static reports-workspace reports-history">
      <div className="section-heading"><div><h2>Report history</h2><p className="reports-section-description">Find the original export and select Verify PDF to compare a submitted copy.</p></div></div>
      {selectedReport && <Link to="/dashboard/reports#report-history" state={state}>Show all saved reports</Link>}
      {historyState.error && <p className="notice notice-danger" role="alert">Report history could not refresh. {historyState.error}</p>}
      <div className="reports-history-toolbar"><span>{history.length} saved report(s)</span><button type="button" className="btn-secondary" disabled={historyState.loading} onClick={load}>{historyState.loading ? 'Loading history…' : 'Refresh history'}</button></div>
      <div className="table-scroll"><table className="interactive-table reports-history-table" aria-label="Generated report history"><colgroup><col style={{ width: '16%' }} /><col style={{ width: '28%' }} /><col style={{ width: '22%' }} /><col style={{ width: '13%' }} /><col style={{ width: '21%' }} /></colgroup><thead><tr><th>Generated</th><th>Type / file</th><th>Report details</th><th>Status</th><th>Review</th></tr></thead><PaginatedBody pageSize={5}>{history.length === 0 && <tr><td colSpan="5" className="empty-cell">{historyState.loading ? 'Loading report history…' : historyState.error ? 'Report history is unavailable.' : 'No registered reports yet.'}</td></tr>}{history.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}<span className="table-subline">{item.generated_by_name}</span></td><td><strong>{item.report_type}</strong><span className="table-subline">{item.filename}</span><SavedReportActions report={item} table
        onPreview={item.report_type === 'Official SF2' ? async () => setSF2Preview(await api.get(`/reports/history/${item.id}/preview`)) : undefined} /><details className="reports-technical-details"><summary>Integrity hash</summary><p className="table-subline">{item.sha256 || 'Unavailable'}</p></details></td><td>{Object.entries(item.parameters || {}).map(([key, value]) => <span className="table-subline" key={key}><strong>{({ starts_on: 'From', ends_on: 'To', school_year: 'School year', school_year_id: 'School year ID', school_id: 'School ID', term_order: 'Term', enrollment_id: 'Enrollment ID', grade: 'Grade', section: 'Section', year: 'Year', month: 'Month', role: 'Population' })[key] || key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())}:</strong> {String(value ?? '—')}</span>)}</td><td><span className="tag tag-gray">{item.status}</span>{item.reviewed_by_name && <span className="table-subline">{item.reviewed_by_name}</span>}</td><td>{['admin', 'records_officer'].includes(auth.role()) ? <div><input className="input-field" aria-label={`Review note for ${item.filename}`} placeholder="Review note" value={review[item.id] || ''} onChange={(event) => setReview((current) => ({ ...current, [item.id]: event.target.value }))} /><select className="input-field" aria-label={`Set review status for ${item.filename}`} value="" onChange={(event) => markReport(item, event.target.value)}><option value="" disabled>Set status…</option>{['Reviewed', 'Approved', 'Rejected', 'Superseded'].map((status) => <option key={status} value={status}>{status}</option>)}</select></div> : (item.review_note || 'Awaiting records review')}</td></tr>)}</PaginatedBody></table></div>
    </section>
    {sf2Preview && <Modal label="Official SF2 preview" onClose={() => setSF2Preview(null)}>
      <div className="modal-card enrollment-detail-modal"><OfficialSF2Preview preview={sf2Preview} onClose={() => setSF2Preview(null)} /></div>
    </Modal>}
    <DeferredReport id="learner-reports" title="Annex G learner reports"><AnnexGWorkspace /></DeferredReport>
  </div>;
}
