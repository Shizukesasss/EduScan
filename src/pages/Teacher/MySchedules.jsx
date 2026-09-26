import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, CheckCircle2, Pencil, Save, Trash2 } from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';

const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const emptyForm = { id: null, grade: '', section: '', subject: '', weekdays: '0,1,2,3,4', start_time: '07:30', end_time: '08:30', late_grace_minutes: 15, absence_cutoff: '08:30', active: true };

export default function MySchedules() {
  const [structure, setStructure] = useState({ grade_levels: [], sections: [], subjects: [] });
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const { showSuccess, showError } = useToast();

  const load = useCallback(async () => {
    try {
      const [references, schedules] = await Promise.all([api.get('/admin/academic-structure'), api.get('/schedules')]);
      setStructure(references); setRows(schedules);
      const grade = references.grade_levels.find((item) => item.active);
      const section = references.sections.find((item) => item.active && item.grade_level_id === grade?.id);
      const isSHS = grade ? ['11', '12'].includes(String(grade.name)) : false;
      const subject = references.subjects.find((item) => item.active && (item.category || 'JHS') === (isSHS ? 'SHS' : 'JHS'));
      setForm((current) => ({ ...current, grade: current.grade || grade?.name || '', section: current.section || section?.name || '', subject: current.subject || subject?.name || '' }));
    } catch (err) { showError(err.message); }
  }, [showError]);
  useEffect(() => { load(); }, [load]);

  const gradeRecord = structure.grade_levels.find((item) => item.name === form.grade);
  const sections = useMemo(() => structure.sections.filter((item) => item.active && item.grade_level_id === gradeRecord?.id), [structure.sections, gradeRecord]);
  const patch = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const changeGrade = (grade) => {
    const record = structure.grade_levels.find((item) => item.name === grade);
    const section = structure.sections.find((item) => item.active && item.grade_level_id === record?.id);
    setForm((current) => ({ ...current, grade, section: section?.name || '' }));
  };
  const toggleDay = (index) => {
    const selected = new Set(form.weekdays.split(',').filter(Boolean).map(Number));
    if (selected.has(index)) selected.delete(index); else selected.add(index);
    patch('weekdays', [...selected].sort().join(','));
  };
  const reset = () => setForm((current) => ({ ...emptyForm, grade: current.grade, section: current.section, subject: current.subject }));
  const save = async (event) => {
    event.preventDefault();
    try {
      await api.post('/schedules', { ...form, teacher_name: auth.name() });
      showSuccess(form.id ? 'Class schedule updated.' : 'Class schedule created.'); reset(); await load();
    } catch (err) { showError(err.message); }
  };
  const edit = (item) => setForm({ ...item });
  const remove = async (id) => {
    try { await api.delete(`/schedules/${id}`); showSuccess('Class schedule removed.'); reset(); await load(); }
    catch (err) { showError(err.message); }
  };

  return <div className="page-stack">
    <section className="card-static"><h2>{form.id ? 'Edit schedule' : 'Add schedule'}</h2>{structure.sections.length === 0 && <div className="notice notice-warning">No section is assigned to this teacher account. Ask an administrator to assign the adviser account under Administration → Academic structure.</div>}<form onSubmit={save}><div className="form-grid three-columns">
      <label><span className="field-label">Grade level</span><select className="input-field" value={form.grade} onChange={(event) => changeGrade(event.target.value)}>{structure.grade_levels.filter((item) => item.active).map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
      <label><span className="field-label">Section</span><select className="input-field" value={form.section} onChange={(event) => patch('section', event.target.value)}>{sections.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
      <label><span className="field-label">{['11', '12'].includes(String(form.grade)) ? 'Track' : 'Subject'}</span><select className="input-field" value={form.subject} onChange={(event) => patch('subject', event.target.value)}>{structure.subjects.filter((item) => item.active && (item.category || 'JHS') === (['11', '12'].includes(String(form.grade)) ? 'SHS' : 'JHS')).map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
      <label><span className="field-label">Class start</span><input className="input-field" type="time" value={form.start_time} onChange={(event) => patch('start_time', event.target.value)} required /></label>
      <label><span className="field-label">Class end</span><input className="input-field" type="time" value={form.end_time} onChange={(event) => patch('end_time', event.target.value)} required /></label>
      <label><span className="field-label">Late grace (minutes)</span><input className="input-field" type="number" min="0" max="180" value={form.late_grace_minutes} onChange={(event) => patch('late_grace_minutes', Number(event.target.value))} required /></label>
      <label><span className="field-label">Authorized absence cutoff</span><input className="input-field" type="time" min={form.start_time} max={form.end_time} value={form.absence_cutoff || ''} onChange={(event) => patch('absence_cutoff', event.target.value)} required /></label>
    </div><fieldset className="weekday-fieldset"><legend className="field-label">Meeting days</legend>{dayNames.map((name, index) => <label className="checkbox-field" key={name}><input type="checkbox" checked={form.weekdays.split(',').includes(String(index))} onChange={() => toggleDay(index)} /><span>{name}</span></label>)}</fieldset><div className="modal-actions">{form.id && <button type="button" className="btn-secondary" onClick={reset}>Cancel edit</button>}<button className="btn-primary" disabled={!form.grade || !form.section || !form.subject || !form.weekdays}><Save size={16} /> Save schedule</button></div></form></section>
    <section className="card-static"><h2>My saved schedules</h2><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Class</th><th>Days</th><th>Time</th><th>Late after</th><th>Absence close</th><th /></tr></thead><tbody>{rows.length === 0 && <tr><td colSpan="6" className="empty-cell">No schedule has been created for an assigned section.</td></tr>}{rows.map((item) => <tr key={item.id}><td><strong>Grade {item.grade} {item.section}</strong><span className="table-subline">{item.subject}</span></td><td>{item.weekdays.split(',').map((day) => dayNames[Number(day)]).join(', ')}</td><td>{item.start_time}–{item.end_time}</td><td>{item.late_grace_minutes} minutes</td><td>{item.absence_cutoff || item.end_time}</td><td><div className="action-row"><button className="btn-link" onClick={() => edit(item)}><Pencil size={14} /> Edit</button><button className="btn-link danger-link" onClick={() => remove(item.id)}><Trash2 size={14} /> Remove</button></div></td></tr>)}</tbody></table></div></section>
  </div>;
}
