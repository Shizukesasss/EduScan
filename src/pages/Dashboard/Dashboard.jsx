import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useState } from 'react';
import { api, displayTime, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import './Dashboard.css';

export default function Dashboard() {
  const [data, setData] = useState({ rows: [], events: [], sms: {} });
  const [health, setHealth] = useState(null);
  const { showError } = useToast();
  const load = useCallback(() => Promise.all([api.get(`/dashboard?date=${localDate()}`), api.get('/health')])
    .then(([dashboard, status]) => { setData(dashboard); setHealth(status); })
    .catch((err) => showError(err.message)), [showError]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const learners = data.rows.filter((row) => row.role === 'Student');
  const personnel = data.rows.filter((row) => row.role !== 'Student');
  const checkedIn = (row) => Boolean(row.time_in);
  const sms = data.sms || {};
  const smsAccepted = (sms.accepted || 0) + (sms.processed || 0) + (sms.sent || 0);
  const smsFailed = (sms.failed || 0) + (sms.exhausted || 0);
  const date = localDate();

  return <div className="admin-overview animate-fade-in">
    <div className="admin-overview__heading">
      <div className="admin-overview__title">
        <h1>Overview</h1>
        <time dateTime={date}>{date}</time>
      </div>
      <button className="btn-primary" type="button" onClick={() => window.open('/scanner', '_blank')}>
        Open gate station
      </button>
    </div>

    <section className="admin-overview__health" aria-label="System health">
      <div className="admin-overview__health-item">
        <span>Database</span>
        <strong>{health?.database || 'Checking'}</strong>
      </div>
      <div className="admin-overview__health-item">
        <span>LBPH</span>
        <strong className={health?.biometric_enabled ? 'is-healthy' : ''}>
          {health ? (health.biometric_enabled ? 'Enabled' : 'Disabled') : 'Checking'}
        </strong>
      </div>
      <div className="admin-overview__health-item admin-overview__health-model">
        <span>Active model</span>
        <strong>{health?.active_model || 'No active model'}</strong>
        {!health?.active_model && <small>Enroll people to create the first model.</small>}
      </div>
    </section>

    <dl className="admin-overview__summary" aria-label="Today’s attendance and SMS summary">
      <div className="admin-overview__stat">
        <dt>Learners with time-in</dt>
        <dd>{learners.filter(checkedIn).length} / {learners.length}</dd>
      </div>
      <div className="admin-overview__stat admin-overview__stat-late">
        <dt>Late learners today</dt>
        <dd>{learners.filter((row) => row.status === 'Late').length}</dd>
      </div>
      <div className="admin-overview__stat">
        <dt>Personnel with time-in</dt>
        <dd>{personnel.filter(checkedIn).length} / {personnel.length}</dd>
      </div>
      <div className="admin-overview__stat admin-overview__stat-sms">
        <dt>SMS delivered / accepted / failed</dt>
        <dd>
          <span><strong>{sms.delivered || 0}</strong><small>Delivered</small></span>
          <span><strong>{smsAccepted}</strong><small>Accepted</small></span>
          <span><strong>{smsFailed}</strong><small>Failed</small></span>
        </dd>
      </div>
    </dl>

    <div className="admin-overview__workspace">
      <section className="admin-overview__events" aria-labelledby="admin-overview-events-title">
        <div className="admin-overview__section-heading">
          <h2 id="admin-overview-events-title">Recent gate events</h2>
          <time dateTime={date}>{date}</time>
        </div>
        <div className="table-scroll">
          <table className="interactive-table" aria-label="Recent gate events">
            <thead>
              <tr><th>Time</th><th>Person</th><th>Role</th><th>Event</th><th>Status</th></tr>
            </thead>
            <PaginatedBody>
              {data.events.length === 0 && <tr><td colSpan="5" className="empty-cell">No gate events recorded today.</td></tr>}
              {data.events.map((event) => <tr key={event.id}>
                <td>{displayTime(event.time)}</td>
                <td><strong>{event.person}</strong></td>
                <td>{event.role}</td>
                <td>{event.direction}</td>
                <td><span className={`tag ${event.status === 'Late' ? 'tag-warning' : event.status === 'Absent' ? 'tag-danger' : 'tag-success'}`}>{event.status}</span></td>
              </tr>)}
            </PaginatedBody>
          </table>
        </div>
      </section>

      <aside className="admin-overview__support" aria-label="Reporting and gateway actions">
        <section aria-labelledby="admin-overview-sf2-title">
          <h2 id="admin-overview-sf2-title">SF2 generation</h2>
          <p>Generate a real official XLSX from the database after roster and daily-close validation.</p>
          <a className="btn-secondary" href="/dashboard/reports">Open SF2 reports</a>
        </section>
        <section aria-labelledby="admin-overview-sms-title">
          <h2 id="admin-overview-sms-title">Android SMS status</h2>
          <p>Queued and failed messages remain visible for authorized retry and reconciliation.</p>
          <a className="btn-secondary" href="/dashboard/setup">Open system setup</a>
        </section>
      </aside>
    </div>
  </div>;
}
