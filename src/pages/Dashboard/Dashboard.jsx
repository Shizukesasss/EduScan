import PaginatedBody from '../../components/Common/PaginatedBody';
import { SkeletonBar, SkeletonRows } from '../../components/Common/Skeleton';
import useSlowLoading from '../../hooks/useSlowLoading';
import { useCallback, useEffect, useState } from 'react';
import { api, displayTime, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import './Dashboard.css';

export default function Dashboard() {
  const [data, setData] = useState({ rows: [], events: [], sms: {} });
  const [snapshot, setSnapshot] = useState({ loading: true, error: '', updatedAt: null });
  const { showError } = useToast();
  const load = useCallback(() => api.get(`/dashboard?date=${localDate()}`)
    .then((dashboard) => { setData(dashboard); setSnapshot({ loading: false, error: '', updatedAt: new Date() }); })
    .catch((err) => { setSnapshot((current) => ({ ...current, loading: false, error: err.message })); showError(err.message); }), [showError]);

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

  const hasSnapshot = Boolean(snapshot.updatedAt);
  const slowInitialLoad = useSlowLoading(snapshot.loading && !hasSnapshot);
  const value = (number) => (hasSnapshot ? number : slowInitialLoad ? <SkeletonBar width="42px" height={24} /> : '—');
  const learnersIn = learners.filter(checkedIn).length;
  const personnelIn = personnel.filter(checkedIn).length;
  const percent = (part, total) => (total ? Math.round((part / total) * 100) : 0);

  const countStatus = (...statuses) => learners.filter((row) => statuses.includes(row.status)).length;
  const breakdown = [
    { key: 'present', label: 'Present', count: countStatus('Present', 'Time Out') },
    { key: 'late', label: 'Late', count: countStatus('Late') },
    { key: 'absent', label: 'Absent', count: countStatus('Absent') },
    { key: 'excused', label: 'Excused', count: countStatus('Excused') },
    { key: 'noscan', label: 'No scan yet', count: countStatus('No scan') },
  ];
  const categorized = breakdown.reduce((sum, item) => sum + item.count, 0);
  if (learners.length > categorized) breakdown.push({ key: 'other', label: 'Other', count: learners.length - categorized });
  const attendanceRate = percent(countStatus('Present', 'Time Out', 'Late'), learners.length);
  const donutRadius = 40;
  const donutLength = 2 * Math.PI * donutRadius;
  let donutOffset = 0;
  const donutSegments = breakdown.filter((item) => item.count > 0).map((item) => {
    const length = (item.count / learners.length) * donutLength;
    const segment = { ...item, length, offset: donutOffset };
    donutOffset += length;
    return segment;
  });

  return <div className="admin-overview animate-fade-in">
    <div className="admin-overview__heading">
      <div className="admin-overview__title">
        <h1>Overview</h1>
        <time dateTime={date}>{new Date(`${date}T12:00:00`).toLocaleDateString('en-PH', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</time>
      </div>
      <div className="admin-overview__actions">
        <p className={`admin-overview__feedback${snapshot.error ? ' is-error' : ''}`} role={snapshot.loading || snapshot.error ? 'status' : undefined}>
          <span>
            {snapshot.loading ? 'Loading today’s overview…' : snapshot.error
              ? `${hasSnapshot ? `Refresh failed. Showing the snapshot from ${snapshot.updatedAt.toLocaleString('en-PH')}.` : 'Today’s overview is unavailable.'} ${snapshot.error}`
              : <>Updated <time dateTime={snapshot.updatedAt.toISOString()}>{snapshot.updatedAt.toLocaleTimeString('en-PH')}</time> · Refreshes every 15 seconds</>}
          </span>
        </p>
        <button className="btn-primary" type="button" onClick={() => window.open('/scanner', '_blank')}>
           Open gate station
        </button>
      </div>
    </div>

    <dl aria-busy={snapshot.loading} className="admin-overview__summary" aria-label="Today’s attendance and SMS summary">
      <div className="admin-overview__stat admin-overview__stat-learners">
        <dt>Learners with time-in</dt>
        <dd>{value(learnersIn)} <span className="admin-overview__denominator">/ {value(learners.length)}</span></dd>
      </div>
      <div className="admin-overview__stat admin-overview__stat-late">
        <dt>Late learners today</dt>
        <dd>{value(learners.filter((row) => row.status === 'Late').length)}</dd>
      </div>
      <div className="admin-overview__stat admin-overview__stat-personnel">
        <dt>Personnel with time-in</dt>
        <dd>{value(personnelIn)} <span className="admin-overview__denominator">/ {value(personnel.length)}</span></dd>
      </div>
      <div className="admin-overview__stat admin-overview__stat-sms">
        <dt>SMS delivery today</dt>
        <dd>
          <span className="is-delivered"><strong>{value(sms.delivered || 0)}</strong><small>Delivered</small></span>
          <span><strong>{value(smsAccepted)}</strong><small>Accepted</small></span>
          <span className="is-failed"><strong>{value(smsFailed)}</strong><small>Failed</small></span>
        </dd>
      </div>
    </dl>

    <div className="admin-overview__workspace">
      <section className="admin-overview__events" aria-labelledby="admin-overview-events-title">
        <div className="admin-overview__section-heading">
          <h2 id="admin-overview-events-title">Recent gate events</h2>
          <span className="admin-overview__table-note">Today’s recorded movements</span>
        </div>
        <div className="table-scroll">
          <table className="interactive-table" aria-label="Recent gate events">
            <thead>
              <tr><th>Time</th><th>Person</th><th>Role</th><th>Event</th><th>Status</th></tr>
            </thead>
            <PaginatedBody>
              {slowInitialLoad && data.events.length === 0 && <SkeletonRows rows={5} cols={5} />}
              {!slowInitialLoad && data.events.length === 0 && <tr><td colSpan="5" className="empty-cell">{snapshot.loading ? 'Loading gate events…' : !hasSnapshot ? 'Gate events are unavailable. The next refresh will retry.' : 'No gate events recorded today.'}</td></tr>}
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

      <aside className="admin-overview__support" aria-label="Reporting, gateway actions and attendance summary">
        <section aria-labelledby="admin-overview-sf2-title">
          <h2 id="admin-overview-sf2-title">SF2 generation</h2>
          <p>Generate an official attendance workbook after roster and daily-close validation.</p>
          <a className="btn-secondary" href="/dashboard/reports">Open SF2 reports</a>
        </section>
        <section aria-labelledby="admin-overview-sms-title">
          <h2 id="admin-overview-sms-title">Android SMS status</h2>
          <p>Queued and failed messages remain visible for authorized retry and reconciliation.</p>
          <a className="btn-secondary" href="/dashboard/setup">Open system setup</a>
        </section>
        <section className="admin-overview__chart-section" aria-labelledby="admin-overview-chart-title">
          <h2 id="admin-overview-chart-title">Learner attendance today</h2>
          <div className="admin-overview__chart">
            <svg viewBox="0 0 100 100" role="img" aria-label={hasSnapshot ? `Attendance rate ${attendanceRate} percent of ${learners.length} learners` : 'Attendance chart unavailable'}>
              <circle className="admin-overview__donut-track" cx="50" cy="50" r={donutRadius} />
              {hasSnapshot && donutSegments.map((segment) => <circle key={segment.key} className={`admin-overview__donut-segment is-${segment.key}`} cx="50" cy="50" r={donutRadius} tabIndex={0} aria-label={`${segment.label}: ${segment.count}`}
                strokeDasharray={`${segment.length} ${donutLength - segment.length}`} strokeDashoffset={-segment.offset} />)}
            </svg>
            <div className="admin-overview__chart-center">
              <strong>{hasSnapshot && learners.length ? `${attendanceRate}%` : '—'}</strong>
              <span>attended</span>
            </div>
          </div>
          <ul className="admin-overview__legend">
            {breakdown.map((item) => <li key={item.key} className={`is-${item.key}`} tabIndex={0}>
              <span className={`admin-overview__swatch is-${item.key}`} aria-hidden="true" />
              <span className="admin-overview__legend-label">{item.label}</span>
              <strong>{value(item.count)}</strong>
              <span className="admin-overview__legend-percent">{hasSnapshot ? `${percent(item.count, learners.length)}%` : '—'}</span>
            </li>)}
          </ul>
        </section>
      </aside>
    </div>
  </div>;
}
