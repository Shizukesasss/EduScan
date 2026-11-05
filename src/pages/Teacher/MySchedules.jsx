import PaginatedBody from '../../components/Common/PaginatedBody';
import PageHeading from '../../components/Common/PageHeading';
import RequestFeedback from '../../components/Common/RequestFeedback';
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export default function MySchedules() {
  const [rows, setRows] = useState([]);
  const [request, setRequest] = useState({ loading: true, error: '' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setRequest({ loading: true, error: '' });
    api.get('/schedules').then(data => {
      if (!cancelled) { setRows(data); setRequest({ loading: false, error: '' }); }
    }).catch(error => { if (!cancelled) setRequest({ loading: false, error: error.message }); });
    return () => { cancelled = true; };
  }, [attempt]);
  return <div className="page-stack">
    <PageHeading title="My schedules" description="Your assigned classes and attendance times. Contact the administrator to request a schedule change." />
    <RequestFeedback {...request} label="your schedules" onRetry={() => setAttempt(value => value + 1)} />
    {!request.loading && !request.error && <section className="card-static">
      <div className="section-heading"><h2>Class schedules</h2><span className="tag tag-gray">{rows.length} assigned</span></div>
      <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Grade &amp; section</th><th>Subject</th><th>Days</th><th>Time</th><th>Late grace</th><th>Absence cutoff</th><th>Status</th></tr></thead><PaginatedBody>
        {!rows.length && <tr><td colSpan="7" className="empty-cell">No teaching schedule is assigned yet. Ask an administrator to check your class assignments.</td></tr>}
        {rows.map(item => <tr key={item.id}><td>Grade {item.grade} — {item.section}</td><td>{item.subject}</td><td>{item.weekdays.split(',').map(day => dayNames[Number(day)]).join(', ')}</td><td>{item.start_time} – {item.end_time}</td><td>{item.late_grace_minutes} minutes</td><td>{item.absence_cutoff || item.end_time}</td><td><span className={`tag ${item.active ? 'tag-success' : 'tag-gray'}`}>{item.active ? 'Active' : 'Inactive'}</span></td></tr>)}
      </PaginatedBody></table></div>
    </section>}
  </div>;
}
