import React, { useState, useEffect } from 'react';
import { Pencil, Trash2, Save, Users, BookOpen, Layers, UserPlus, CheckCircle2, ShieldAlert, AlertTriangle } from 'lucide-react';
import { api } from '../../api/client';

function ReferenceCard({ title, rows, columns, onEdit, onDelete, children }) {
  return (
    <section className="card-static mb-4">
      <h2 className="mb-2 text-lg font-bold">{title}</h2>
      {children}
      <div className="table-scroll mt-4">
        <table className="interactive-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column.replaceAll('_', ' ')}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id}>
                {columns.map((column) => (
                  <td key={column}>{String(item[column] ?? '—')}</td>
                ))}
                <td>
                  <div className="flex gap-2 justify-end">
                    <button type="button" className="btn-link" onClick={() => onEdit(item)}>
                      <Pencil size={14} /> Edit
                    </button>
                    {onDelete && (
                      <button type="button" className="btn-link text-danger" onClick={() => onDelete(item.id)}>
                        <Trash2 size={14} /> Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 1} className="empty-cell text-center p-4">No records found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Field({ label, type = 'text', value, onChange, required = false }) {
  return (
    <label>
      <span className="field-label">{label} {required && <span className="text-danger">*</span>}</span>
      <input
        className="input-field"
        type={type}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        required={required}
      />
    </label>
  );
}

function ConfirmModal({ title, message, onConfirm, onCancel, danger = false }) {
  const [checked, setChecked] = useState(false);
  return (
    <div className="modal-backdrop">
      <div className="modal-card" style={{ maxWidth: 460 }}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">{danger ? 'This action requires confirmation' : 'Confirm action'}</p>
            <h2>{title}</h2>
          </div>
          {danger ? <ShieldAlert color="#dc2626" /> : <AlertTriangle color="#d97706" />}
        </div>
        <p className="section-copy" style={{ marginTop: '0.75rem' }}>{message}</p>
        <label className="checkbox-field" style={{ marginTop: '1rem' }}>
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          <span>I understand and confirm this action</span>
        </label>
        <div className="modal-actions" style={{ marginTop: '1rem' }}>
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button
            type="button"
            className={danger ? 'btn-danger' : 'btn-primary'}
            disabled={!checked}
            onClick={onConfirm}
          >
            {danger ? <Trash2 size={16} /> : <CheckCircle2 size={16} />}
            {danger ? 'Yes, proceed' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AcademicSetupTab({ structure, reloadStructure, onSuccess, onError }) {
  // State for Academic Structure CRUD
  const [grade, setGrade] = useState({ id: null, name: '', sequence: 0, active: true });
  const [subject, setSubject] = useState({ id: null, code: '', name: '', category: 'JHS', active: true });
  const [section, setSection] = useState({
    id: null,
    grade_level_id: structure?.grade_levels?.[0]?.id || '',
    name: '',
    adviser_user_id: '',
    adviser_name: '',
    active: true
  });

  // State for Student CRUD
  const [student, setStudent] = useState({
    id: null,
    external_id: '',
    lrn: '',
    full_name: '',
    sex: 'M',
    role: 'Student',
    grade: '',
    section: '',
    active: true
  });
  const [studentsList, setStudentsList] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [loadingStudents, setLoadingStudents] = useState(false);

  const [confirm, setConfirm] = useState(null);

  useEffect(() => {
    fetchStudents();
    fetchTeachers();
  }, []);

  const fetchTeachers = async () => {
    try {
      const res = await api.get('/admin/users');
      setTeachers(res.filter(u => u.role === 'teacher' || u.role === 'admin'));
    } catch (err) {
      console.error(err);
    }
  };

  const fetchStudents = async () => {
    setLoadingStudents(true);
    try {
      const res = await api.get('/admin/persons');
      // Filter strictly to students to avoid showing teachers here
      setStudentsList(res.filter(p => p.role === 'Student'));
    } catch (err) {
      onError(err.message || 'Failed to fetch students.');
    } finally {
      setLoadingStudents(false);
    }
  };

  const saveStructure = async (path, value, reset, label) => {
    try {
      await api.post(`/admin/${path}`, value);
      reset();
      onSuccess(`${label} saved successfully.`);
      await reloadStructure();
    } catch (err) {
      onError(err.message || `Failed to save ${label.toLowerCase()}.`);
    }
  };

  const removeStructure = (path, id, label) => {
    setConfirm({
      title: `Delete ${label}`,
      message: `Are you sure you want to permanently delete this ${label}? This cannot be undone.`,
      danger: true,
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.delete(`/admin/reference/${path}/${id}`);
          onSuccess('Record deleted.');
          await reloadStructure();
        } catch (err) {
          onError(err.message || 'Failed to delete record.');
        }
      },
    });
  };

  const saveStudent = async () => {
    try {
      if (!student.external_id) {
        student.external_id = 'STU-' + Date.now(); // Auto-generate if empty to satisfy backend
      }
      if (student.id) {
        await api.patch(`/persons/${student.id}`, student);
        onSuccess('Student updated successfully.');
      } else {
        await api.post('/persons', student);
        onSuccess('Student created successfully.');
      }
      setStudent({
        id: null, external_id: '', lrn: '', full_name: '', sex: 'M', role: 'Student', grade: '', section: '', active: true
      });
      fetchStudents();
    } catch (err) {
      onError(err.message || 'Failed to save student.');
    }
  };

  const firstGrade = structure?.grade_levels?.[0]?.id || '';

  return (
    <div className="academic-setup-container max-w-5xl mx-auto py-4">
      <div className="flex flex-col gap-6">

        {/* Grade Levels */}
        <ReferenceCard
          title="Grade Levels"
          rows={structure?.grade_levels || []}
          columns={['name', 'sequence']}
          onEdit={setGrade}
          onDelete={(id) => removeStructure('grade-levels', id, 'Grade Level')}
        >
          <div className="form-grid two-columns mb-3">
            <Field label="Grade level (e.g. 7)" value={grade.name} onChange={(value) => setGrade({ ...grade, name: value })} />
            <Field label="Sort sequence" type="number" value={grade.sequence} onChange={(value) => setGrade({ ...grade, sequence: Number(value) })} />
          </div>
          <button type="button" className="btn btn-primary" onClick={() => saveStructure('grade-levels', grade, () => setGrade({ id: null, name: '', sequence: 0, active: true }), 'Grade level')}>
            <Save size={16} /> Save Grade Level
          </button>
        </ReferenceCard>

        {/* Subjects */}
        <ReferenceCard
          title="Subjects"
          rows={structure?.subjects || []}
          columns={['code', 'name', 'category']}
          onEdit={setSubject}
          onDelete={(id) => removeStructure('subjects', id, 'Subject')}
        >
          <div className="form-grid three-columns mb-3">
            <Field label="Subject code" value={subject.code} onChange={(value) => setSubject({ ...subject, code: value })} />
            <Field label="Subject name" value={subject.name} onChange={(value) => setSubject({ ...subject, name: value })} />
            <label>
              <span className="field-label">Category</span>
              <select className="input-field" value={subject.category || 'JHS'} onChange={(e) => setSubject({ ...subject, category: e.target.value })}>
                <option value="JHS">JHS (Grades 7-10)</option>
                <option value="SHS">SHS Track (Grades 11-12)</option>
              </select>
            </label>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => saveStructure('subjects', subject, () => setSubject({ id: null, code: '', name: '', category: 'JHS', active: true }), 'Subject')}>
            <Save size={16} /> Save Subject
          </button>
        </ReferenceCard>

        {/* Sections */}
        <ReferenceCard
          title="Sections"
          rows={structure?.sections || []}
          columns={['grade', 'name', 'adviser_name']}
          onEdit={(item) => setSection({ ...item, adviser_user_id: item.adviser_user_id || '' })}
          onDelete={(id) => removeStructure('sections', id, 'Section')}
        >
          <div className="form-grid three-columns mb-3">
            <label>
              <span className="field-label">Grade level</span>
              <select className="input-field" value={section.grade_level_id} onChange={(e) => setSection({ ...section, grade_level_id: Number(e.target.value) })}>
                {structure?.grade_levels?.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <Field label="Section Name" value={section.name} onChange={(value) => setSection({ ...section, name: value })} />
            <label>
              <span className="field-label">Adviser Account (Optional)</span>
              <select className="input-field" value={section.adviser_user_id || ''} onChange={(e) => setSection({ ...section, adviser_user_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Unassigned</option>
                {teachers?.map((item) => (
                  <option key={item.id} value={item.id}>{item.full_name} ({item.username})</option>
                ))}
              </select>
            </label>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => saveStructure('sections', section, () => setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', active: true }), 'Section')}>
            <Save size={16} /> Save Section
          </button>
        </ReferenceCard>

        {/* Student Roster (Manual Entry) */}
        <section className="card-static mb-4">
          <h2 className="mb-2 text-lg font-bold">Student Roster Management</h2>
          <div className="form-grid three-columns mb-3">
            <Field label="Full Name (Last, First M.)" value={student.full_name} onChange={(val) => setStudent({ ...student, full_name: val })} required />
            <Field label="LRN (Optional)" value={student.lrn} onChange={(val) => setStudent({ ...student, lrn: val })} />
            <label>
              <span className="field-label">Sex</span>
              <select className="input-field" value={student.sex} onChange={(e) => setStudent({ ...student, sex: e.target.value })}>
                <option value="M">Male</option>
                <option value="F">Female</option>
              </select>
            </label>

            <label>
              <span className="field-label">Grade</span>
              <select className="input-field" value={student.grade} onChange={(e) => setStudent({ ...student, grade: e.target.value })} required>
                <option value="">Select Grade...</option>
                {structure?.grade_levels?.map(g => (
                  <option key={g.id} value={g.name}>{g.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Section</span>
              <select className="input-field" value={student.section} onChange={(e) => setStudent({ ...student, section: e.target.value })} required>
                <option value="">Select Section...</option>
                {structure?.sections?.filter(s => !student.grade || s.grade === student.grade).map(s => (
                  <option key={s.id} value={s.name}>{s.name}</option>
                ))}
              </select>
            </label>
            <Field label="Student ID (Optional)" value={student.external_id} onChange={(val) => setStudent({ ...student, external_id: val })} />
          </div>

          <div className="flex gap-2">
            <button type="button" className="btn btn-primary" onClick={saveStudent} disabled={!student.full_name || !student.grade || !student.section}>
              <UserPlus size={16} /> {student.id ? 'Update Student' : 'Add Student'}
            </button>
            {student.id && (
              <button type="button" className="btn btn-secondary" onClick={() => setStudent({ id: null, external_id: '', lrn: '', full_name: '', sex: 'M', role: 'Student', grade: '', section: '', active: true })}>
                Cancel Edit
              </button>
            )}
          </div>

          <div className="table-scroll mt-4">
            <table className="interactive-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>LRN / ID</th>
                  <th>Sex</th>
                  <th>Grade</th>
                  <th>Section</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {loadingStudents ? (
                  <tr><td colSpan="6" className="text-center p-4">Loading students...</td></tr>
                ) : studentsList.length === 0 ? (
                  <tr><td colSpan="6" className="text-center p-4">No students found.</td></tr>
                ) : (
                  studentsList.map(s => (
                    <tr key={s.id}>
                      <td className="font-medium">{s.full_name}</td>
                      <td>{s.lrn || s.external_id}</td>
                      <td>{s.sex}</td>
                      <td>{s.grade}</td>
                      <td>{s.section}</td>
                      <td>
                        <button type="button" className="btn-link" onClick={() => setStudent(s)}>
                          <Pencil size={14} /> Edit
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

      </div>
      {confirm && (
        <ConfirmModal
          title={confirm.title}
          message={confirm.message}
          danger={confirm.danger}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
