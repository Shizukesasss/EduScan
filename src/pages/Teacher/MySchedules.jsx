import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../contexts/useToast';

const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export default function MySchedules() {
  const [rows, setRows] = useState([]);
  const { showError } = useToast();
  const load = useCallback(() => api.get('/schedules').then(setRows).catch(error => showError(error.message)), [showError]);
  useEffect(() => { load(); }, [load]);
  return <section className="card-static"><h2>My class schedules</h2><p className="section-copy">Schedules are created and managed by the administrator. Only schedules linked to your teacher account are shown.</p>
    <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Grade &amp; section</th><th>Subject</th><th>Days</th><th>Time</th><th>Late grace</th><th>Absence cutoff</th><th>Status</th></tr></thead><tbody>
      {!rows.length && <tr><td colSpan="7" className="empty-cell">The administrator has not assigned a teaching schedule to your account.</td></tr>}
      {rows.map(item => <tr key={item.id}><td>Grade {item.grade} - Section {item.section}</td><td>{item.subject}</td><td>{item.weekdays.split(',').map(day => dayNames[Number(day)]).join(', ')}</td><td>{item.start_time} - {item.end_time}</td><td>{item.late_grace_minutes} minutes</td><td>{item.absence_cutoff || item.end_time}</td><td>{item.active ? 'Active' : 'Inactive'}</td></tr>)}
    </tbody></table></div></section>;
}
