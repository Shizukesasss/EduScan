import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../contexts/useToast';

const blank = { id: null, teacher_user_id: '', section_id: '', subject: '', weekdays: '0,1,2,3,4', start_time: '07:30', end_time: '08:30', late_grace_minutes: 15, absence_cutoff: '08:30', active: true };
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export default function ClassScheduleManager() {
  const [form, setForm] = useState(blank);
  const [rows, setRows] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [structure, setStructure] = useState({ sections: [], subjects: [] });
  const { showSuccess, showError } = useToast();
  const load = useCallback(() => Promise.all([api.get('/schedules'), api.get('/admin/users'), api.get('/admin/academic-structure')])
    .then(([schedules, users, academic]) => { setRows(schedules); setTeachers(users.filter(user => user.active && user.role === 'teacher').sort((a,b) => a.full_name.localeCompare(b.full_name))); setStructure(academic); })
    .catch(error => showError(error.message)), [showError]);
  useEffect(() => { load(); }, [load]);
  const patch = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const sections = structure.sections.filter(item => item.active).sort((a,b) => String(a.grade).localeCompare(String(b.grade), undefined, { numeric: true }) || a.name.localeCompare(b.name));
  const save = async event => {
    event.preventDefault();
    const teacher = teachers.find(item => item.id === Number(form.teacher_user_id));
    const section = sections.find(item => item.id === Number(form.section_id));
    if (!teacher || !section) return showError('Choose an active teacher account and section.');
    try { await api.post('/schedules', { ...form, teacher_user_id: teacher.id, teacher_name: teacher.full_name, grade: section.grade, section: section.name }); showSuccess('Teaching schedule saved. It is now visible in the teacher workspace and Reports.'); setForm(blank); await load(); }
    catch (error) { showError(error.message); }
  };
  const edit = item => setForm({ ...item, teacher_user_id: item.teacher_user_id || teachers.find(teacher => teacher.full_name === item.teacher_name)?.id || '', section_id: sections.find(section => section.grade === item.grade && section.name === item.section)?.id || '', absence_cutoff: item.absence_cutoff || item.end_time });
  const remove = async id => { try { await api.delete(`/schedules/${id}`); setForm(blank); await load(); } catch (error) { showError(error.message); } };
  return <section className="card-static"><h2>Class schedules</h2><p className="section-copy">Administrator-managed teaching schedules. Select the actual teacher account so the schedule appears only in that teacher's workspace.</p><form onSubmit={save}><div className="form-grid three-columns">
    <label><span className="field-label">Teacher</span><select className="input-field" required value={form.teacher_user_id} onChange={event => patch('teacher_user_id', event.target.value)}><option value="">Choose a teacher</option>{teachers.map(item => <option key={item.id} value={item.id}>{item.full_name} ({item.username})</option>)}</select></label>
    <label><span className="field-label">Grade &amp; section</span><select className="input-field" required value={form.section_id} onChange={event => patch('section_id', event.target.value)}><option value="">Choose a grade and section</option>{sections.map(item => <option key={item.id} value={item.id}>Grade {item.grade} - Section {item.name}</option>)}</select></label>
    <label><span className="field-label">Subject</span><select className="input-field" required value={form.subject} onChange={event => patch('subject', event.target.value)}><option value="">Choose a subject</option>{[...structure.subjects].filter(item => item.active).sort((a,b) => a.name.localeCompare(b.name)).map(item => <option key={item.id}>{item.name}</option>)}</select></label>
    <label><span className="field-label">Class start</span><input title="Choose a time using the time picker" className="input-field" type="time" required value={form.start_time} onChange={event => patch('start_time', event.target.value)} /></label>
    <label><span className="field-label">Class end</span><input title="Choose a time using the time picker" className="input-field" type="time" required min={form.start_time} value={form.end_time} onChange={event => patch('end_time', event.target.value)} /></label>
    <label><span className="field-label">Late grace (minutes)</span><input className="input-field" type="number" required min="0" max="180" placeholder="e.g. 15" value={form.late_grace_minutes} onChange={event => patch('late_grace_minutes', Number(event.target.value))} /></label>
    <label><span className="field-label">Absence cutoff</span><input title="Choose a time using the time picker" className="input-field" type="time" required min={form.start_time} max={form.end_time} value={form.absence_cutoff} onChange={event => patch('absence_cutoff', event.target.value)} /></label>
  </div><fieldset className="weekday-fieldset"><legend>Meeting days</legend>{days.map((day,index) => <label className="checkbox-field" key={day}><input type="checkbox" checked={form.weekdays.split(',').includes(String(index))} onChange={() => { const selected = new Set(form.weekdays.split(',').filter(Boolean)); if (selected.has(String(index))) selected.delete(String(index)); else selected.add(String(index)); patch('weekdays', [...selected].sort().join(',')); }} /><span>{day}</span></label>)}</fieldset><div className="modal-actions">{form.id && <button type="button" className="btn-secondary" onClick={() => setForm(blank)}>Cancel edit</button>}<button className="btn-primary" disabled={!form.weekdays}>Save schedule</button></div></form>
  <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Teacher</th><th>Class</th><th>Subject</th><th>Days / time</th><th>Actions</th></tr></thead><tbody>{!rows.length && <tr><td colSpan="5" className="empty-cell">No class schedules have been created.</td></tr>}{rows.map(item => <tr key={item.id}><td>{item.teacher_name}</td><td>Grade {item.grade} - Section {item.section}</td><td>{item.subject}</td><td>{item.weekdays.split(',').map(day => days[Number(day)]).join(', ')}<span className="table-subline">{item.start_time} - {item.end_time}</span></td><td><button className="btn-link" onClick={() => edit(item)}>Edit</button><button className="btn-link danger-link" onClick={() => remove(item.id)}>Remove</button></td></tr>)}</tbody></table></div></section>;
}
