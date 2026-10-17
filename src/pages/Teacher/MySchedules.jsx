import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pencil, Save, Trash2 } from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';

const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const emptyForm = { id: null, grade: '', section: '', subject: '', weekdays: '0,1,2,3,4', start_time: '07:30', end_time: '08:30', late_grace_minutes: 15, absence_cutoff: '08:30', active: true };

export default function MySchedules() {
  const [structure, setStructure] = useState({ grade_levels: [], sections: [], subjects: [], school_years: [], subject_assignments: [] });
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const { showSuccess, showError } = useToast();

  const load = useCallback(() => Promise.all([
    api.get('/admin/academic-structure?context=grading'),
    api.get('/schedules'),
  ]).then(([references, schedules]) => {
      setStructure(references); setRows(schedules);
      const year = references.school_years.filter((item) => item.active)
        .sort((a, b) => String(b.starts_on).localeCompare(String(a.starts_on)))[0];
      const assignments = references.subject_assignments.filter((item) =>
        item.school_year_id === year?.id && item.teacher_user_id === references.current_user_id);
      const assignedSections = references.sections.filter((item) =>
        item.active && assignments.some((assignment) => assignment.section_id === item.id));
      const firstSection = assignedSections[0];
      setForm((current) => ({
        ...current,
        grade: assignedSections.some((item) => item.grade === current.grade) ? current.grade : firstSection?.grade || '',
        section: assignedSections.some((item) => item.grade === current.grade && item.name === current.section)
          ? current.section : firstSection?.name || '',
      }));
    }).catch((err) => showError(err.message)), [showError]);
  useEffect(() => { load(); }, [load]);

  const gradeRecord = structure.grade_levels.find((item) => item.name === form.grade);
  const activeSchoolYear = useMemo(() => [...(structure.school_years || [])]
    .filter((item) => item.active)
    .sort((a, b) => String(b.starts_on).localeCompare(String(a.starts_on)))[0], [structure.school_years]);
  const activeAssignments = useMemo(() => (structure.subject_assignments || [])
    .filter((item) => item.school_year_id === activeSchoolYear?.id
      && item.teacher_user_id === structure.current_user_id), [structure.subject_assignments, structure.current_user_id, activeSchoolYear]);
  const assignedSectionIds = useMemo(() => new Set(activeAssignments.map((item) => item.section_id)), [activeAssignments]);
  const assignedSections = useMemo(() => structure.sections.filter((item) =>
    item.active && assignedSectionIds.has(item.id)), [structure.sections, assignedSectionIds]);
  const grades = structure.grade_levels.filter((item) => item.active
    && assignedSections.some((section) => section.grade_level_id === item.id));
  const sections = useMemo(() => assignedSections.filter((item) => item.grade_level_id === gradeRecord?.id), [assignedSections, gradeRecord]);
  const selectedSection = sections.find((item) => item.name === form.section);
  const teacherSubjectIds = useMemo(() => new Set(activeAssignments.map((item) => item.subject_id)), [activeAssignments]);
  const subjectOptions = useMemo(() => {
    if (teacherSubjectIds.size !== 1 || !selectedSection) return [];
    const assignedIds = new Set(activeAssignments
      .filter((item) => item.section_id === selectedSection.id)
      .map((item) => item.subject_id));
    return structure.subjects.filter((item) => item.active && assignedIds.has(item.id));
  }, [structure.subjects, activeAssignments, selectedSection, teacherSubjectIds]);
  const selectedSubject = subjectOptions.some((item) => item.name === form.subject)
    ? form.subject : subjectOptions[0]?.name || '';
  const teacherAssignmentConflict = teacherSubjectIds.size > 1;
  const patch = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const changeGrade = (grade) => {
    const record = structure.grade_levels.find((item) => item.name === grade);
    const section = assignedSections.find((item) => item.grade_level_id === record?.id);
    setForm((current) => ({ ...current, grade, section: section?.name || '', subject: '' }));
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
      await api.post('/schedules', { ...form, subject: selectedSubject, teacher_name: auth.name() });
      showSuccess(form.id ? 'Class schedule updated.' : 'Class schedule created.'); reset(); await load();
    } catch (err) { showError(err.message); }
  };
  const edit = (item) => setForm({ ...item });
  const remove = async (id) => {
    try { await api.delete(`/schedules/${id}`); showSuccess('Class schedule removed.'); reset(); await load(); }
    catch (err) { showError(err.message); }
  };

  return <div className="page-stack">
    <section className="card-static"><h2>{form.id ? 'Edit schedule' : 'Add schedule'}</h2>{assignedSections.length === 0 && <div className="notice notice-warning">No subject sections are assigned to you for the active school year. Ask an administrator to update Subject Teaching Assignments.</div>}{teacherAssignmentConflict && <div className="notice notice-warning" role="alert">Your account has active assignments in more than one subject for this school year. Ask an administrator to correct them before managing schedules.</div>}{!teacherAssignmentConflict && assignedSections.length > 0 && !subjectOptions.length && <div className="notice notice-warning" role="status">No subject is assigned to you for this section and active school year. Ask an administrator to update Subject Teaching Assignments.</div>}<form onSubmit={save}><div className="form-grid three-columns">
      <label><span className="field-label">Grade level</span><select className="input-field" value={form.grade} onChange={(event) => changeGrade(event.target.value)}>{grades.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
      <label><span className="field-label">Section</span><select className="input-field" value={form.section} onChange={(event) => patch('section', event.target.value)}>{sections.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
      <label><span className="field-label">Subject</span><select className="input-field" value={selectedSubject} onChange={(event) => patch('subject', event.target.value)} disabled={!subjectOptions.length}>{!subjectOptions.length && <option value="">No assigned subject</option>}{subjectOptions.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
      <label><span className="field-label">Class start</span><input className="input-field" type="time" value={form.start_time} onChange={(event) => patch('start_time', event.target.value)} required /></label>
      <label><span className="field-label">Class end</span><input className="input-field" type="time" value={form.end_time} onChange={(event) => patch('end_time', event.target.value)} required /></label>
      <label><span className="field-label">Late grace (minutes)</span><input className="input-field" type="number" min="0" max="180" value={form.late_grace_minutes} onChange={(event) => patch('late_grace_minutes', Number(event.target.value))} required /></label>
      <label><span className="field-label">Authorized absence cutoff</span><input className="input-field" type="time" min={form.start_time} max={form.end_time} value={form.absence_cutoff || ''} onChange={(event) => patch('absence_cutoff', event.target.value)} required /></label>
    </div><fieldset className="weekday-fieldset"><legend className="field-label">Meeting days</legend>{dayNames.map((name, index) => <label className="checkbox-field" key={name}><input type="checkbox" checked={form.weekdays.split(',').includes(String(index))} onChange={() => toggleDay(index)} /><span>{name}</span></label>)}</fieldset><div className="modal-actions">{form.id && <button type="button" className="btn-secondary" onClick={reset}>Cancel edit</button>}<button className="btn-primary" disabled={!form.grade || !form.section || !selectedSubject || !form.weekdays}><Save size={16} /> Save schedule</button></div></form></section>
    <section className="card-static"><h2>My saved schedules</h2><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Class</th><th>Days</th><th>Time</th><th>Late after</th><th>Absence close</th><th /></tr></thead><tbody>{rows.length === 0 && <tr><td colSpan="6" className="empty-cell">No schedule has been created for an assigned section.</td></tr>}{rows.map((item) => {
      const canManage = structure.sections.some((section) => section.grade === item.grade && section.name === item.section);
      return <tr key={item.id}><td><strong>Grade {item.grade} {item.section}</strong><span className="table-subline">{item.subject}</span></td><td>{item.weekdays.split(',').map((day) => dayNames[Number(day)]).join(', ')}</td><td>{item.start_time}–{item.end_time}</td><td>{item.late_grace_minutes} minutes</td><td>{item.absence_cutoff || item.end_time}</td><td>{canManage ? <div className="action-row"><button className="btn-link" onClick={() => edit(item)}><Pencil size={14} /> Edit</button><button className="btn-link danger-link" onClick={() => remove(item.id)}><Trash2 size={14} /> Remove</button></div> : <span className="tag tag-gray">View only</span>}</td></tr>;
    })}</tbody></table></div></section>
  </div>;
}
