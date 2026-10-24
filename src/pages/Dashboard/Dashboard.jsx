import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useState } from 'react';
import { Camera, Clock3, FileSpreadsheet, MessageSquareText, ShieldCheck, UserRoundCheck } from 'lucide-react';
import { api, displayTime, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function Dashboard() {
  const [data, setData] = useState({ rows: [], events: [], sms: {} });
  const [health, setHealth] = useState(null);
  const { showError } = useToast();
  const load = useCallback(() => Promise.all([api.get(`/dashboard?date=${localDate()}`), api.get('/health')])
    .then(([dashboard, status]) => { setData(dashboard); setHealth(status); })
    .catch((err) => showError(err.message)), [showError]);
  useEffect(() => { load(); const timer = window.setInterval(load, 15000); return () => clearInterval(timer); }, [load]);
  const learners = data.rows.filter((row) => row.role === 'Student');
  const personnel = data.rows.filter((row) => row.role !== 'Student');
  const checkedIn = (row) => Boolean(row.time_in);
  return <div className="page-stack animate-fade-in">
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}><button className="btn-primary" onClick={() => window.open('/scanner', '_blank')}><Camera size={17} /> Open gate station</button></div>
    <div className="notice notice-blue"><ShieldCheck size={19} /><div><strong>Database: {health?.database || 'checking'}.</strong> LBPH is {health?.biometric_enabled ? 'enabled' : 'disabled'}; {health?.active_model ? `active model ${health.active_model}.` : 'enroll people to create the first model.'}</div></div>
    <div className="metric-grid"><div className="metric-card"><UserRoundCheck size={21} color="var(--accent-blue)" /><span>Learners with time-in</span><strong>{learners.filter(checkedIn).length}/{learners.length}</strong></div><div className="metric-card"><Clock3 size={21} color="#b45309" /><span>Late learners today</span><strong>{learners.filter((row) => row.status === 'Late').length}</strong></div><div className="metric-card"><ShieldCheck size={21} color="var(--success)" /><span>Personnel with time-in</span><strong>{personnel.filter(checkedIn).length}/{personnel.length}</strong></div><div className="metric-card"><MessageSquareText size={21} color="var(--secondary-color)" /><span>SMS delivered / accepted / failed</span><strong>{data.sms.delivered || 0} / {(data.sms.accepted || 0) + (data.sms.processed || 0) + (data.sms.sent || 0)} / {(data.sms.failed || 0) + (data.sms.exhausted || 0)}</strong></div></div>
    <div className="dashboard-grid"><section className="card-static"><div className="section-heading"><div><p className="eyebrow">Today · {localDate()}</p><h2>Recent gate events</h2></div><Camera size={23} /></div><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Time</th><th>Person</th><th>Role</th><th>Event</th><th>Status</th></tr></thead><PaginatedBody>{data.events.length === 0 && <tr><td colSpan="5" className="empty-cell">No gate events recorded today.</td></tr>}{data.events.map((event) => <tr key={event.id}><td>{displayTime(event.time)}</td><td><strong>{event.person}</strong></td><td>{event.role}</td><td>{event.direction}</td><td><span className={`tag ${event.status === 'Late' ? 'tag-warning' : event.status === 'Absent' ? 'tag-danger' : 'tag-success'}`}>{event.status}</span></td></tr>)}</PaginatedBody></table></div></section><aside className="page-stack"><section className="card-static"><div className="section-heading"><div><p className="eyebrow">Reporting</p><h2>SF2 generation</h2></div><FileSpreadsheet size={23} /></div><p className="section-copy">Generate a real official XLSX from the database after roster and daily-close validation.</p><button className="btn-secondary" onClick={() => { window.location.href = '/dashboard/reports'; }}>Open SF2 reports</button></section><section className="card-static"><div className="section-heading"><div><p className="eyebrow">Gateway</p><h2>Android SMS status</h2></div><MessageSquareText size={23} /></div><p className="section-copy">Queued and failed messages remain visible for authorized retry and reconciliation.</p><button className="btn-secondary" onClick={() => { window.location.href = '/dashboard/setup'; }}>Open system setup</button></section></aside></div>
  </div>;
}
