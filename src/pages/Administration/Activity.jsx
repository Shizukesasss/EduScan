import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import PaginatedBody from '../../components/Common/PaginatedBody';
import SavedReportActions from '../../components/Reports/SavedReportActions';
import { ReturnLink } from '../../components/Common/ReturnNavigation';

const emptyFilters = { kind: 'all', starts_on: '', ends_on: '', account: '', outcome: '', actor: '', action: '', entity: '' };
const localTime = new Intl.DateTimeFormat('en-PH', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Asia/Manila' });

function activityFilters(query) {
  const params = new URLSearchParams(query);
  return Object.fromEntries(Object.entries(emptyFilters).map(([key, value]) => [key, params.get(key) || value]));
}

function ActivityDetails({ item, role }) {
  if (item.kind === 'sign-ins') return <dl>
    <dt>Method</dt><dd>{item.method || 'Unavailable'}</dd>
    <dt>Source IP</dt><dd>{item.source || 'Unavailable'}</dd>
  </dl>;
  const snapshots = [['Before', item.before], ['After', item.after]].filter(([, data]) => data && Object.keys(data).length);
  const canOpenReport = item.entity === 'GeneratedReport' && item.entity_id && ['admin', 'records_officer'].includes(role);
  const canOpenFaceSettings = item.entity === 'BiometricRuntimeSettings' && role === 'admin';
  if (!snapshots.length && !canOpenReport && !canOpenFaceSettings) return <span>No additional details recorded.</span>;
  return <>
    {snapshots.map(([label, data]) => <div key={label}><strong>{label}</strong>
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(data, null, 2)}</pre>
    </div>)}
    {canOpenReport &&
      <ReturnLink to={`/dashboard/reports?report=${encodeURIComponent(item.entity_id)}#report-history`}>Find report in history</ReturnLink>}
    {canOpenFaceSettings && <ReturnLink to="/dashboard/setup?tab=biometrics#face-enrollments">Open face enrollment settings</ReturnLink>}
  </>;
}

export default function Activity({ role }) {
  const canSeeSignIns = role === 'admin';
  const { pathname, search, hash, state, key } = useLocation();
  const navigate = useNavigate();
  const appliedQuery = state?.activityQuery || '';
  const [filters, setFilters] = useState(() => activityFilters(appliedQuery));
  const [accounts, setAccounts] = useState([]);
  const [accountError, setAccountError] = useState('');
  const [result, setResult] = useState({ rows: [], has_more: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [showReports, setShowReports] = useState(false);
  const [reports, setReports] = useState({ rows: [], error: '', loading: false });

  useEffect(() => {
    if (!canSeeSignIns || filters.kind !== 'sign-ins') return undefined;
    let active = true;
    api.get('/admin/users').then(users => { if (active) { setAccounts(users); setAccountError(''); } })
      .catch(err => { if (active) setAccountError(err.message); });
    return () => { active = false; };
  }, [canSeeSignIns, filters.kind]);

  useEffect(() => {
    let active = true;
    setFilters(activityFilters(appliedQuery));
    setError('');
    setExportError('');
    setLoading(true);
    api.get('/admin/activity' + appliedQuery).then(data => {
      if (active) setResult(data);
    }).catch(err => {
      if (active) { setResult({ rows: [], has_more: false }); setError(err.message); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [appliedQuery, key]);

  const field = (key, value) => setFilters(previous => ({ ...previous, [key]: value }));
  const apply = event => {
    event.preventDefault();
    const keys = ['kind', 'starts_on', 'ends_on'];
    if (filters.kind === 'sign-ins') keys.push('account', 'outcome');
    if (filters.kind === 'changes') keys.push('actor', 'action', 'entity');
    const params = new URLSearchParams(keys.filter(key => filters[key]).map(key => [key, filters[key].trim()]));
    const query = '?' + params.toString();
    navigate({ pathname, search, hash }, {
      replace: appliedQuery === query,
      state: { ...state, activityQuery: query },
    });
  };
  const loadReports = async () => {
    setReports(previous => ({ ...previous, error: '', loading: true }));
    try {
      const rows = await api.get('/admin/activity/reports');
      setReports({ rows, error: '', loading: false });
    } catch (err) {
      setReports({ rows: [], error: err.message, loading: false });
    }
  };
  const exportPdf = async () => {
    setExportError('');
    setExporting(true);
    try {
      await api.download('/admin/activity.pdf' + appliedQuery, 'administrative-activity.pdf');
      if (showReports) await loadReports();
    }
    catch (err) { setExportError(err.message); }
    finally { setExporting(false); }
  };

  return <section className="card-static">
    <h2>Activity log</h2>
    <form onSubmit={apply}>
      <div className="form-grid three-columns">
        <label><span className="field-label">Activity type</span><select className="input-field" value={filters.kind} onChange={event => field('kind', event.target.value)}>
          <option value="all">All activity</option><option value="changes">Administrative changes</option>
          {canSeeSignIns && <option value="sign-ins">Sign-ins</option>}
        </select></label>
        <label><span className="field-label">From (Philippine time)</span><input className="input-field" type="date" value={filters.starts_on} max={filters.ends_on || undefined} onChange={event => field('starts_on', event.target.value)} /></label>
        <label><span className="field-label">Through (Philippine time)</span><input className="input-field" type="date" value={filters.ends_on} min={filters.starts_on || undefined} onChange={event => field('ends_on', event.target.value)} /></label>
        {filters.kind === 'sign-ins' && <>
          <label><span className="field-label">Account</span><select className="input-field" value={filters.account} onChange={event => field('account', event.target.value)}>
            <option value="">All accounts</option>{accounts.map(user => <option key={user.id} value={user.id}>{user.username}</option>)}
          </select></label>
          <label><span className="field-label">Result</span><select className="input-field" value={filters.outcome} onChange={event => field('outcome', event.target.value)}>
            <option value="">All results</option><option>Succeeded</option><option>Failed</option>
          </select></label>
        </>}
        {filters.kind === 'changes' && [['actor', 'Actor', 180], ['action', 'Action', 80], ['entity', 'Record type', 80]].map(([key, label, length]) =>
          <label key={key}><span className="field-label">{label}</span><input className="input-field" maxLength={length} value={filters[key]} onChange={event => field(key, event.target.value)} /></label>)}
      </div>
      <div className="action-row">
        <button type="submit" className="btn-secondary" disabled={loading}>Apply filters</button>
        <button type="button" className="btn-secondary" onClick={exportPdf} disabled={loading || Boolean(error) || exporting}>
          {exporting ? 'Exporting PDF…' : 'Export filtered PDF'}
        </button>
      </div>
    </form>
    <p className="muted-small" role="status">{loading ? 'Loading activity…' : result.has_more
      ? 'Showing the latest 500 matches. The PDF includes up to 5,000 matches using the applied filters.'
      : `${result.rows.length} matching entries. The PDF uses the applied filters.`}</p>
    {(error || exportError || (filters.kind === 'sign-ins' && accountError)) &&
      <p role="alert" className="notice notice-danger">{error || exportError || accountError}</p>}
    <div className="table-scroll"><table aria-label="Activity log" className="interactive-table">
      <thead><tr><th>Time (PHT)</th><th>Actor or account</th><th>Action</th><th>Record type</th><th>Summary</th></tr></thead>
      <PaginatedBody resetKey={key} columnCount={5}>
        {!loading && !error && result.rows.length === 0 && <tr><td colSpan={5} className="empty-cell">No activity matches these filters.</td></tr>}
        {!loading && result.rows.map(item => <tr key={item.id}><td>{localTime.format(new Date(item.time))}</td>
          <td>{item.account || item.name || 'Unknown'}{item.role && <span className="table-subline">{item.role}</span>}</td>
          <td>{item.action}</td><td>{item.entity}</td>
          <td><details><summary>{item.summary}</summary><ActivityDetails item={item} role={role} /></details></td>
        </tr>)}
      </PaginatedBody>
    </table></div>
    <details onToggle={event => {
      setShowReports(event.currentTarget.open);
      if (event.currentTarget.open) void loadReports();
    }}>
      <summary>Saved activity PDFs</summary>
      {reports.loading && <p role="status">Loading saved PDFs…</p>}
      {reports.error && <p role="alert">{reports.error}</p>}
      {!reports.loading && !reports.error && !reports.rows.length && <p>No saved activity PDFs.</p>}
      {reports.rows.length > 0 && <div className="table-scroll"><table className="interactive-table">
        <thead><tr><th>Exported (PHT)</th><th>Report</th><th>Actions</th></tr></thead>
        <PaginatedBody columnCount={3} pageSize={5}>{reports.rows.map(report => <tr key={report.id}>
          <td>{localTime.format(new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(report.created_at) ? report.created_at : report.created_at + 'Z'))}</td>
          <td>{report.report_type}<small className="table-subline">{report.filename}</small></td>
          <td><SavedReportActions report={report} table /></td>
        </tr>)}</PaginatedBody>
      </table></div>}
    </details>
  </section>;
}
