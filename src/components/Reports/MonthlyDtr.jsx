import { useEffect, useState } from 'react';
import { api, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import PaginatedBody from '../Common/PaginatedBody';
import { searchAttendanceRows } from '../../services/attendanceSearch';

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const PUNCHES = {
  am_arrival: 'AM arrival', am_departure: 'AM departure',
  pm_arrival: 'PM arrival', pm_departure: 'PM departure',
};

export default function MonthlyDtr({ role, onDownload }) {
  const [roster, setRoster] = useState(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [month, setMonth] = useState(() => localDate().slice(0, 7));

  useEffect(() => {
    let active = true;
    api.get(`/dtr/employees?${new URLSearchParams({ role })}`)
      .then(rows => { if (active) setRoster(rows); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [role]);

  const results = searchAttendanceRows((roster || []).map(employee => ({
    ...employee, external_id: employee.employee_id,
  })), search);
  const selected = roster?.find(employee => String(employee.id) === employeeId);
  if (selected && !results.some(employee => employee.id === selected.id)) results.unshift(selected);

  return <div className="dtr-workspace">
    <div className="form-grid three-columns">
      <label><span className="field-label">Find employee</span><input className="input-field" type="search" placeholder="Name or Employee ID" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <label><span className="field-label">Employee</span><select className="input-field" value={employeeId} disabled={!roster} onChange={event => setEmployeeId(event.target.value)}>
        <option value="">{!roster && !error ? 'Loading employees…' : results.length ? 'Select an employee' : 'No matching employees'}</option>
        {results.map(employee => <option key={employee.id} value={employee.id}>{employee.full_name} ({employee.employee_id}){employee.active ? '' : ' — inactive'}</option>)}
      </select></label>
      <label><span className="field-label">Month</span><input className="input-field" type="month" value={month} onChange={event => setMonth(event.target.value)} /></label>
    </div>
    {error && <p className="notice notice-danger" role="alert">{error}</p>}
    {employeeId && <EmployeeDtr key={employeeId} employeeId={employeeId} month={month} onDownload={onDownload} />}
  </div>;
}

function EmployeeDtr({ employeeId, month, onDownload }) {
  const [schedule, setSchedule] = useState(null);
  const [scheduleError, setScheduleError] = useState('');
  const [revision, setRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const { showSuccess, showError } = useToast();
  const base = `/dtr/${employeeId}`;

  useEffect(() => {
    let active = true;
    api.get(`${base}/schedule`).then(rows => {
      if (active) setSchedule(Object.fromEntries(rows.map(row => [row.weekday, row])));
    }).catch(error => { if (active) setScheduleError(error.message); });
    return () => { active = false; };
  }, [base]);

  const edit = (weekday, field, value) => setSchedule(current => ({
    ...current, [weekday]: { weekday, ...current[weekday], [field]: value },
  }));

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await api.put(`${base}/schedule`, Object.values(schedule).filter(row => row.start_time || row.end_time));
      setRevision(value => value + 1);
      showSuccess('Form 48 duty hours saved.');
    } catch (error) {
      showError(error.message);
    } finally {
      setSaving(false);
    }
  }

  return <>
    <details className="dtr-duty-hours">
      <summary>Recurring duty hours</summary>
      <p className="section-copy">Set the employee’s official hours by weekday. Leave both times blank to use the existing personnel schedule for that day. These hours apply to Form 48 review.</p>
      {scheduleError && <p className="notice notice-danger" role="alert">{scheduleError}</p>}
      {!schedule && !scheduleError && <p role="status">Loading duty hours…</p>}
      {schedule && <form onSubmit={save}>
        <fieldset disabled={saving} className="dtr-schedule-grid" aria-label="Weekday duty hours">
          <div className="dtr-weekday dtr-schedule-labels" aria-hidden="true"><span>Weekday</span><span>Duty start</span><span>Duty end</span></div>
          {WEEKDAYS.map((day, weekday) => <div className="dtr-weekday" key={day}>
            <span>{day}</span>
            <input className="input-field" type="time" aria-label={`${day} duty start`} value={schedule[weekday]?.start_time?.slice(0, 5) || ''} required={Boolean(schedule[weekday]?.end_time)} onChange={event => edit(weekday, 'start_time', event.target.value)} />
            <input className="input-field" type="time" aria-label={`${day} duty end`} value={schedule[weekday]?.end_time?.slice(0, 5) || ''} required={Boolean(schedule[weekday]?.start_time)} onChange={event => edit(weekday, 'end_time', event.target.value)} />
          </div>)}
        </fieldset>
        <button className="btn-secondary" disabled={saving}>{saving ? 'Saving…' : 'Save duty hours'}</button>
      </form>}
    </details>
    {month && <DtrPreview key={`${month}/${revision}`} base={base} month={month} onDownload={onDownload} saving={saving} />}
  </>;
}

function DtrPreview({ base, month, onDownload, saving }) {
  const [days, setDays] = useState(null);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const { showError } = useToast();
  const [year, monthNumber] = month.split('-');
  const query = new URLSearchParams({ year, month: monthNumber }).toString();

  useEffect(() => {
    let active = true;
    api.get(`${base}/preview?${query}`).then(data => { if (active) setDays(data.days); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [base, query]);

  async function download(format) {
    setDownloading(true);
    try {
      await api.download(`${base}/export?${query}&format=${format}`, `Form-48-${month}.${format}`);
      onDownload();
    } catch (err) {
      showError(err.message);
    } finally {
      setDownloading(false);
    }
  }

  const needsReview = days?.filter(day => day.review || day.missing.length).length;
  return <>
    <div className="reports-preview-heading"><h3>Daily punches</h3>
      {error ? <p className="notice notice-danger" role="alert">{error}</p> : <p className="muted-small" role="status">
        {days ? `${needsReview} day${needsReview === 1 ? '' : 's'} flagged for review.` : 'Loading Form 48 preview…'}
      </p>}
    </div>
    {days && <div className="table-scroll"><table className="interactive-table dtr-preview" aria-label="Form 48 daily punches">
      <thead><tr><th>Date</th>{Object.values(PUNCHES).map(label => <th key={label}>{label}</th>)}
        <th>AM Status</th><th>PM Status</th><th>Review</th></tr></thead>
      <PaginatedBody pageSize={10}>{days.map(day => <tr key={day.date}>
        <td>{day.date}{day.status && <span className="table-subline">{day.status}</span>}</td>
        {Object.keys(PUNCHES).map(key => <td key={key}>{day[key]?.slice(0, 5) || '—'}</td>)}
        <td>{day.am_status || '—'}</td><td>{day.pm_status || '—'}</td>
        <td>{day.review || (day.missing.length ? `Missing ${day.missing.map(key => PUNCHES[key]).join(', ')}` : '—')}</td>
      </tr>)}</PaginatedBody>
    </table></div>}
    <div className="action-row dtr-downloads">
      <button className="btn-primary" disabled={!days || downloading || saving} onClick={() => download('pdf')}>Download Form 48 PDF</button>
      <button className="btn-secondary" disabled={!days || downloading || saving} onClick={() => download('xlsx')}>Download Form 48 Excel</button>
    </div>
  </>;
}
