import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, ArchiveRestore, CheckCircle2, ChevronDown, ChevronUp,
  Database, Download, FileUp, KeyRound, Pencil, Plus, Save,
  ShieldAlert, Trash2, UserCog, Users, UserCheck, ChevronsUpDown
} from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';

const tabs = [
  ['people', 'People & records'],
  ['accounts', 'Accounts'],
  ['academic', 'Academic structure'],
  ['roster', 'Roster import'],
  ['recovery', 'Backup & recovery'],
];
const emptyPerson = {
  external_id: '', lrn: '', full_name: '', sex: 'Female', role: 'Student',
  grade: '', section: '', assignment: '', guardian_phone: '',
  enrollment_status: 'Regular', enrollment_start_date: '', enrollment_end_date: '',
  transfer_school: '', biometric_consent: false,
};
const emptyUser = { username: '', password: '', role: 'teacher', full_name: '', active: true };

// ─── Confirmation Modal ─────────────────────────────────────────────────────
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

// ─── Active Badge ───────────────────────────────────────────────────────────
function ActiveBadge({ active }) {
  return <span className={`tag ${active ? 'tag-success' : 'tag-gray'}`}>{active ? 'Yes' : 'No'}</span>;
}

// ─── Shared form primitives ─────────────────────────────────────────────────
function Field({ label, value, onChange, type = 'text', required = false, disabled = false }) {
  return (
    <label>
      <span className="field-label">{label}</span>
      <input className="input-field" type={type} value={value ?? ''} onChange={(e) => onChange(e.target.value)} required={required} disabled={disabled} />
    </label>
  );
}
function SelectField({ label, value, onChange, options }) {
  const values = options.includes('admin')
    ? [...new Set([...options, 'records_officer', 'privacy_officer', 'ict'])]
    : options;
  return (
    <label>
      <span className="field-label">{label}</span>
      <select className="input-field" value={value} onChange={(e) => onChange(e.target.value)}>
        {values.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
  );
}

// ─── Administration Root ────────────────────────────────────────────────────
export default function Administration() {
  const [active, setActive] = useState('people');
  const [people, setPeople] = useState([]);
  const [users, setUsers] = useState([]);
  const [structure, setStructure] = useState({ school_years: [], grading_periods: [], grade_levels: [], sections: [], subjects: [] });
  const [imports, setImports] = useState([]);
  const [disposals, setDisposals] = useState([]);
  const [backups, setBackups] = useState([]);
  const { showSuccess, showError } = useToast();

  const load = useCallback(async () => {
    try {
      const [personRows, accountRows, academicRows, importRows, disposalRows, backupRows] = await Promise.all([
        api.get('/admin/persons'), api.get('/admin/users'), api.get('/admin/academic-structure'),
        api.get('/admin/roster/imports'), api.get('/admin/disposals'), api.get('/admin/backups'),
      ]);
      setPeople(personRows); setUsers(accountRows); setStructure(academicRows);
      setImports(importRows); setDisposals(disposalRows); setBackups(backupRows);
    } catch (err) { showError(err.message); }
  }, [showError]);

  useEffect(() => { load(); }, [load]);
  const success = (msg) => showSuccess(msg);
  const fail    = (err) => showError(err.message);

  return (
    <div className="page-stack">
      <div className="setup-tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={active === id ? 'active' : ''} onClick={() => setActive(id)}>{label}</button>
        ))}
      </div>
      {active === 'people'   && <PeopleManager people={people} disposals={disposals} reload={load} success={success} fail={fail} />}
      {active === 'accounts' && <AccountManager users={users} reload={load} success={success} fail={fail} />}
      {active === 'academic' && <AcademicManager structure={structure} teachers={users.filter((u) => u.role === 'teacher' && u.active)} reload={load} success={success} fail={fail} />}
      {active === 'roster'   && <RosterManager imports={imports} reload={load} success={success} fail={fail} />}
      {active === 'recovery' && <RecoveryManager backups={backups} reload={load} success={success} fail={fail} />}
    </div>
  );
}

// ─── People Manager ─────────────────────────────────────────────────────────
function PeopleManager({ people, disposals, reload, success, fail }) {
  const [form, setForm] = useState(emptyPerson);
  const [editing, setEditing] = useState(null);
  const [disposal, setDisposal] = useState(null);
  const patch = (field, value) => setForm((c) => ({ ...c, [field]: value }));
  const edit  = (item) => { setEditing(item.id); setForm(Object.fromEntries(Object.keys(emptyPerson).map((k) => [k, item[k] ?? emptyPerson[k]]))); };
  const save  = async (event) => {
    event.preventDefault();
    try {
      const payload = { ...form, lrn: form.lrn || null, grade: form.grade || null, section: form.section || null, assignment: form.assignment || null, guardian_phone: form.guardian_phone || null, enrollment_start_date: form.enrollment_start_date || null, enrollment_end_date: form.enrollment_end_date || null, transfer_school: form.transfer_school || null };
      if (editing) await api.patch(`/persons/${editing}`, payload); else await api.post('/persons', payload);
      success(editing ? 'School record updated.' : 'School record created.'); setEditing(null); setForm(emptyPerson); await reload();
    } catch (err) { fail(err); }
  };
  const setActive = async (item) => { const data = new FormData(); data.append('active', String(!item.active)); try { await api.post(`/admin/persons/${item.id}/active`, data); success(`${item.full_name} ${item.active ? 'deactivated' : 'reactivated'}.`); await reload(); } catch (err) { fail(err); } };
  return (
    <div className="page-stack">
      <section className="card-static">
        <div className="section-heading"><div><p className="eyebrow">Students, faculty, and personnel</p><h2>{editing ? 'Edit school record' : 'Add school record'}</h2></div><Users size={24} /></div>
        <form onSubmit={save}>
          <div className="form-grid three-columns">
            <Field label="School / employee ID" value={form.external_id} onChange={(v) => patch('external_id', v)} required />
            <Field label="LRN (students)" value={form.lrn} onChange={(v) => patch('lrn', v)} />
            <Field label="Full name" value={form.full_name} onChange={(v) => patch('full_name', v)} required />
            <SelectField label="Sex for SF2" value={form.sex} onChange={(v) => patch('sex', v)} options={['Female', 'Male']} />
            <SelectField label="Role" value={form.role} onChange={(v) => patch('role', v)} options={['Student', 'Faculty', 'Non-teaching Personnel']} />
            <Field label="Guardian phone" value={form.guardian_phone} onChange={(v) => patch('guardian_phone', v)} />
            <Field label="Grade level" value={form.grade} onChange={(v) => patch('grade', v)} required={form.role === 'Student'} />
            <Field label="Section" value={form.section} onChange={(v) => patch('section', v)} required={form.role === 'Student'} />
            <Field label="Office / assignment" value={form.assignment} onChange={(v) => patch('assignment', v)} />
            {form.role === 'Student' && <SelectField label="Enrollment / movement" value={form.enrollment_status} onChange={(v) => patch('enrollment_status', v)} options={['Regular', 'Transferred In', 'Transferred Out']} />}
            {form.role === 'Student' && <Field label="Enrollment / transfer-in date" type="date" value={form.enrollment_start_date} onChange={(v) => patch('enrollment_start_date', v)} />}
            {form.role === 'Student' && <Field label="Transfer-out date" type="date" value={form.enrollment_end_date} onChange={(v) => patch('enrollment_end_date', v)} />}
            {form.role === 'Student' && form.enrollment_status !== 'Regular' && <Field label={form.enrollment_status === 'Transferred In' ? 'Previous school' : 'Receiving school'} value={form.transfer_school} onChange={(v) => patch('transfer_school', v)} />}
            <label className="checkbox-field"><input type="checkbox" checked={form.biometric_consent} onChange={(e) => patch('biometric_consent', e.target.checked)} /><span>Authorized biometric enrollment consent is documented</span></label>
          </div>
          <div className="modal-actions">{editing && <button type="button" className="btn-secondary" onClick={() => { setEditing(null); setForm(emptyPerson); }}>Cancel</button>}<button className="btn-primary"><Save size={16} /> {editing ? 'Save changes' : 'Create record'}</button></div>
        </form>
      </section>
      <section className="card-static">
        <h2>School records</h2>
        <p className="section-copy">Student ID and LRN are unique. Deactivation preserves history, while full disposal removes linked records under a documented authority.</p>
        <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Name</th><th>ID / LRN</th><th>Role / placement</th><th>Movement</th><th>Face samples</th><th>Status</th><th /></tr></thead><tbody>{people.map((item) => <tr key={item.id}><td><strong>{item.full_name}</strong>{item.possible_duplicate && <span className="table-subline duplicate-warning">Possible duplicate name—verify IDs</span>}</td><td>{item.external_id}<span className="table-subline">{item.lrn || 'No LRN'}</span></td><td>{item.role}<span className="table-subline">{item.grade ? `Grade ${item.grade} — ${item.section}` : item.assignment || '—'}</span></td><td>{item.role === 'Student' ? item.enrollment_status : '—'}{item.transfer_school && <span className="table-subline">{item.transfer_school}</span>}</td><td>{item.sample_count}</td><td><span className={`tag ${item.active ? 'tag-success' : 'tag-gray'}`}>{item.active ? 'Active' : 'Inactive'}</span></td><td><details className="action-menu table-action-menu"><summary><ChevronDown size={15} /> Manage</summary><div className="action-menu-panel"><button onClick={() => edit(item)}><Pencil size={14} /> Edit record</button><button onClick={() => setActive(item)}>{item.active ? 'Deactivate record' : 'Reactivate record'}</button><button className="danger-link" onClick={() => setDisposal(item)}><Trash2 size={14} /> Full disposal</button></div></details></td></tr>)}</tbody></table></div>
      </section>
      <section className="card-static"><h2>Record-disposal audit</h2><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Completed</th><th>Anonymous reference</th><th>Authority</th><th>Reason</th><th>Removed</th><th>Actor</th></tr></thead><tbody>{disposals.length === 0 && <tr><td colSpan="6" className="empty-cell">No full record disposal has been performed.</td></tr>}{disposals.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}</td><td>{item.disposal_reference}</td><td>{item.authorization_reference}</td><td>{item.reason}</td><td>{Object.entries(item.removed_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</td><td>{item.actor_name}</td></tr>)}</tbody></table></div></section>
      {disposal && <DisposalModal person={disposal} onClose={() => setDisposal(null)} onDone={async () => { setDisposal(null); success('The selected person and all linked school records were securely disposed.'); await reload(); }} fail={fail} />}
    </div>
  );
}

function DisposalModal({ person, onClose, onDone, fail }) {
  const [reason, setReason] = useState(''); const [reference, setReference] = useState(''); const [confirmation, setConfirmation] = useState('');
  const submit = async (event) => { event.preventDefault(); try { await api.delete(`/admin/persons/${person.id}/records`, { reason, authorization_reference: reference, confirmation }); await onDone(); } catch (err) { fail(err); } };
  return <div className="modal-backdrop"><form className="modal-card" onSubmit={submit}><div className="modal-header"><div><p className="eyebrow">Irreversible authorized disposal</p><h2>Delete all records for {person.full_name}</h2></div><ShieldAlert color="#dc2626" /></div><div className="notice notice-danger">This removes the identity record plus linked face samples/model membership, gate events, corrections, grades, SMS, excuses, and intervention records. Export or back up first when the approved retention schedule requires it.</div><div className="form-grid"><Field label="Documented reason" value={reason} onChange={setReason} required /><Field label="Authorization / disposition reference" value={reference} onChange={setReference} required /><Field label={`Type the school ID ${person.external_id}`} value={confirmation} onChange={setConfirmation} required /></div><div className="modal-actions"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-danger"><Trash2 size={16} /> Permanently dispose records</button></div></form></div>;
}

// ─── Account Manager ────────────────────────────────────────────────────────
function AccountManager({ users, reload, success, fail }) {
  const [form, setForm] = useState(emptyUser); const [editing, setEditing] = useState(null);
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '' });
  const patch = (field, value) => setForm((c) => ({ ...c, [field]: value }));
  const edit  = (item) => { setEditing(item.id); setForm({ username: item.username, password: '', role: item.role, full_name: item.full_name, active: item.active }); };
  const save  = async (event) => { event.preventDefault(); try { if (editing) await api.put(`/admin/users/${editing}`, { role: form.role, full_name: form.full_name, active: form.active, new_password: form.password || null }); else await api.post('/admin/users', form); success(editing ? 'Account updated.' : 'Account created.'); setEditing(null); setForm(emptyUser); await reload(); } catch (err) { fail(err); } };
  const deactivate    = async (item) => { try { await api.delete(`/admin/users/${item.id}`); success(`${item.username} was deactivated.`); await reload(); } catch (err) { fail(err); } };
  const unlock        = async (item) => { try { await api.post(`/admin/users/${item.id}/unlock`, {}); success(`${item.username} was unlocked.`); await reload(); } catch (err) { fail(err); } };
  const changePassword = async (event) => { event.preventDefault(); try { await api.post('/auth/change-password', passwords); auth.passwordChanged(); setPasswords({ current_password: '', new_password: '' }); success('Your password was changed.'); } catch (err) { fail(err); } };
  return (
    <div className="page-stack">
      <section className="card-static">
        <div className="section-heading"><div><p className="eyebrow">Role-based access</p><h2>{editing ? 'Edit account' : 'Create account'}</h2></div><UserCog size={24} /></div>
        <p className="section-copy">Temporary and reset passwords require at least 12 characters with uppercase, lowercase, number, and symbol. The account owner must replace them at next login.</p>
        <form onSubmit={save}>
          <div className="form-grid three-columns">
            <Field label="Username" value={form.username} onChange={(v) => patch('username', v)} disabled={Boolean(editing)} required />
            <Field label={editing ? 'New temporary password (optional)' : 'Temporary password'} type="password" value={form.password} onChange={(v) => patch('password', v)} required={!editing} />
            <Field label="Full name" value={form.full_name} onChange={(v) => patch('full_name', v)} required />
            <SelectField label="Role" value={form.role} onChange={(v) => patch('role', v)} options={['admin', 'teacher', 'scanner']} />
            <label className="checkbox-field"><input type="checkbox" checked={form.active} onChange={(e) => patch('active', e.target.checked)} /><span>Account is active</span></label>
          </div>
          <div className="modal-actions">{editing && <button type="button" className="btn-secondary" onClick={() => { setEditing(null); setForm(emptyUser); }}>Cancel</button>}<button className="btn-primary"><Save size={16} /> Save account</button></div>
        </form>
        <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Security</th><th /></tr></thead><tbody>{users.map((item) => <tr key={item.id}><td>{item.full_name}</td><td>{item.username}</td><td>{item.role}</td><td>{item.active ? 'Active' : 'Inactive'}</td><td>{item.locked_until ? `Locked until ${new Date(item.locked_until).toLocaleString('en-PH')}` : item.must_change_password ? 'Password change required' : 'Ready'}</td><td><details className="action-menu table-action-menu"><summary><ChevronDown size={15} /> Manage</summary><div className="action-menu-panel"><button onClick={() => edit(item)}><Pencil size={14} /> Edit account</button>{item.locked_until && <button onClick={() => unlock(item)}>Unlock account</button>}{item.active && item.username !== 'admin' && <button className="danger-link" onClick={() => deactivate(item)}>Deactivate account</button>}</div></details></td></tr>)}</tbody></table></div>
      </section>
      <section className="card-static">
        <div className="section-heading"><div><p className="eyebrow">Signed in as {auth.name()}</p><h2>Change my password</h2></div><KeyRound size={24} /></div>
        <form onSubmit={changePassword}><div className="form-grid two-columns"><Field label="Current password" type="password" value={passwords.current_password} onChange={(v) => setPasswords((c) => ({ ...c, current_password: v }))} required /><Field label="New strong password" type="password" value={passwords.new_password} onChange={(v) => setPasswords((c) => ({ ...c, new_password: v }))} required /></div><div className="modal-actions"><button className="btn-primary"><KeyRound size={16} /> Change password</button></div></form>
      </section>
    </div>
  );
}

// ─── AcademicCard ───────────────────────────────────────────────────────────
function AcademicCard({ title, eyebrow, columns, rows, onEdit, onDelete, extraActions, form, formNote, onSave, onCancel, isEditing }) {
  const [sortKey, setSortKey] = useState(columns[0]?.key || '');
  const [sortDir, setSortDir] = useState('asc');

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
  };

  const sorted = [...rows].sort((a, b) => {
    const valA = a[sortKey] ?? '';
    const valB = b[sortKey] ?? '';
    const cmp = typeof valA === 'boolean'
      ? Number(valA) - Number(valB)
      : String(valA).localeCompare(String(valB), undefined, { numeric: true });
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return (
    <section className="card-static">
      <div className="section-heading">
        <div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{isEditing ? `Edit — ${title}` : `Add — ${title}`}</h2></div>
        <Database size={22} />
      </div>
      {form}
      {formNote && <p className="section-copy" style={{ marginTop: '0.5rem' }}>{formNote}</p>}
      <div className="modal-actions">
        {isEditing && <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>}
        <button type="button" className="btn-primary" onClick={onSave}><Save size={16} /> Save</button>
      </div>
      <div className="table-scroll" style={{ marginTop: '1.25rem' }}>
        <table className="interactive-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} onClick={() => toggleSort(col.key)} style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    {col.label}
                    {sortKey === col.key
                      ? (sortDir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />)
                      : <ChevronsUpDown size={13} style={{ opacity: 0.35 }} />}
                  </span>
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && <tr><td colSpan={columns.length + 1} className="empty-cell">No {title.toLowerCase()} have been added yet.</td></tr>}
            {sorted.map((item) => (
              <tr key={item.id}>
                {columns.map((col) => (
                  <td key={col.key}>{col.render ? col.render(item[col.key]) : String(item[col.key] ?? '—')}</td>
                ))}
                <td>
                  <details className="action-menu table-action-menu">
                    <summary><ChevronDown size={15} /> Manage</summary>
                    <div className="action-menu-panel">
                      <button onClick={() => onEdit(item)}><Pencil size={14} /> Edit</button>
                      {extraActions && extraActions(item)}
                      <button className="danger-link" onClick={() => onDelete(item)}><Trash2 size={14} /> Delete</button>
                    </div>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ─── Academic Manager ───────────────────────────────────────────────────────
function AcademicManager({ structure, teachers, reload, success, fail }) {
  const firstYear  = structure.school_years[0]?.id  || '';
  const firstGrade = structure.grade_levels[0]?.id  || '';

  const [year,    setYear]    = useState({ id: null, name: '', starts_on: '', ends_on: '', active: true });
  const [period,  setPeriod]  = useState({ id: null, school_year_id: '', name: 'Quarter 1', quarter: 1, starts_on: '', ends_on: '', active: true });
  const [grade,   setGrade]   = useState({ id: null, name: '', sequence: 0, active: true });
  const [section, setSection] = useState({ id: null, grade_level_id: '', name: '', adviser_user_id: '', adviser_name: '', active: true });
  const [subject, setSubject] = useState({ id: null, code: '', name: '', active: true });

  const [adviserModal, setAdviserModal] = useState(null);
  const [newAdviserId, setNewAdviserId] = useState('');
  const [confirm, setConfirm] = useState(null);

  useEffect(() => {
    if (!period.school_year_id && firstYear)  setPeriod((c) => ({ ...c, school_year_id: firstYear }));
    if (!section.grade_level_id && firstGrade) setSection((c) => ({ ...c, grade_level_id: firstGrade }));
  }, [firstYear, firstGrade, period.school_year_id, section.grade_level_id]);

  const confirmSave = (path, value, reset, label) => {
    setConfirm({
      title: `Save ${label}`,
      message: `Are you sure you want to save changes to "${value.name || label}"? This will immediately update the academic structure.`,
      danger: false,
      onConfirm: async () => {
        setConfirm(null);
        try { await api.post(`/admin/${path}`, value); reset(); success(`${label} saved.`); await reload(); }
        catch (err) { fail(err); }
      },
    });
  };

  const confirmDelete = (kind, item, label) => {
    setConfirm({
      title: `Delete ${label}`,
      message: `Are you sure you want to permanently delete "${item.name || label}"? This cannot be undone. Ensure no gradebooks or students are currently linked to it.`,
      danger: true,
      onConfirm: async () => {
        setConfirm(null);
        try { await api.delete(`/admin/reference/${kind}/${item.id}`); success(`${label} deleted.`); await reload(); }
        catch (err) { fail(err); }
      },
    });
  };

  const openAdviserModal = (sec) => { setAdviserModal(sec); setNewAdviserId(sec.adviser_user_id || ''); };

  const saveAdviser = () => {
    if (!adviserModal) return;
    const targetName = newAdviserId
      ? (teachers.find((t) => t.id === Number(newAdviserId))?.full_name || '')
      : 'Unassigned';
    setConfirm({
      title: 'Reassign Adviser',
      message: `Assign "${targetName}" as adviser for Section "${adviserModal.grade} - ${adviserModal.name}"? The previous adviser will immediately lose access to this section.`,
      danger: false,
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.post('/admin/sections', {
            id: adviserModal.id, grade_level_id: adviserModal.grade_level_id,
            name: adviserModal.name, adviser_user_id: newAdviserId ? Number(newAdviserId) : null,
            adviser_name: adviserModal.adviser_name, active: adviserModal.active,
          });
          success(`Adviser for "${adviserModal.grade} - ${adviserModal.name}" updated to ${targetName}.`);
          setAdviserModal(null); await reload();
        } catch (err) { fail(err); }
      },
    });
  };

  return (
    <div className="page-stack">
      <div className="notice notice-blue"><Database size={18} /> These records organize gradebooks by school year, quarter, subject, grade level, and section. In-use references should be deactivated rather than deleted.</div>

      <AcademicCard
        title="School Years" eyebrow="Academic calendar"
        columns={[{ key: 'name', label: 'Name' }, { key: 'starts_on', label: 'Starts' }, { key: 'ends_on', label: 'Ends' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.school_years}
        onEdit={(item) => setYear({ ...item })}
        onDelete={(item) => confirmDelete('school-years', item, 'School Year')}
        form={<div className="form-grid three-columns"><Field label="Name (e.g. 2026-2027)" value={year.name} onChange={(v) => setYear({ ...year, name: v })} /><Field label="Starts" type="date" value={year.starts_on} onChange={(v) => setYear({ ...year, starts_on: v })} /><Field label="Ends" type="date" value={year.ends_on} onChange={(v) => setYear({ ...year, ends_on: v })} /></div>}
        onSave={() => confirmSave('school-years', year, () => setYear({ id: null, name: '', starts_on: '', ends_on: '', active: true }), 'School Year')}
        onCancel={() => setYear({ id: null, name: '', starts_on: '', ends_on: '', active: true })}
        isEditing={Boolean(year.id)}
      />

      <AcademicCard
        title="Grading Periods" eyebrow="Quarters and term dates"
        columns={[{ key: 'school_year', label: 'School Year' }, { key: 'name', label: 'Name' }, { key: 'quarter', label: 'Quarter' }, { key: 'starts_on', label: 'Starts' }, { key: 'ends_on', label: 'Ends' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.grading_periods}
        onEdit={(item) => setPeriod({ ...item })}
        onDelete={(item) => confirmDelete('grading-periods', item, 'Grading Period')}
        form={<div className="form-grid three-columns"><label><span className="field-label">School Year</span><select className="input-field" value={period.school_year_id} onChange={(e) => setPeriod({ ...period, school_year_id: Number(e.target.value) })}>{structure.school_years.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><Field label="Name" value={period.name} onChange={(v) => setPeriod({ ...period, name: v })} /><Field label="Quarter" type="number" value={period.quarter} onChange={(v) => setPeriod({ ...period, quarter: Number(v) })} /><Field label="Starts" type="date" value={period.starts_on} onChange={(v) => setPeriod({ ...period, starts_on: v })} /><Field label="Ends" type="date" value={period.ends_on} onChange={(v) => setPeriod({ ...period, ends_on: v })} /></div>}
        onSave={() => confirmSave('grading-periods', period, () => setPeriod({ id: null, school_year_id: firstYear, name: 'Quarter 1', quarter: 1, starts_on: '', ends_on: '', active: true }), 'Grading Period')}
        onCancel={() => setPeriod({ id: null, school_year_id: firstYear, name: 'Quarter 1', quarter: 1, starts_on: '', ends_on: '', active: true })}
        isEditing={Boolean(period.id)}
      />

      <AcademicCard
        title="Grade Levels" eyebrow="Year levels"
        columns={[{ key: 'name', label: 'Grade Level' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.grade_levels}
        onEdit={(item) => setGrade({ ...item })}
        onDelete={(item) => confirmDelete('grade-levels', item, 'Grade Level')}
        form={<div className="form-grid two-columns"><Field label="Grade level (e.g. 7)" value={grade.name} onChange={(v) => setGrade({ ...grade, name: v })} /><Field label="Sort sequence" type="number" value={grade.sequence} onChange={(v) => setGrade({ ...grade, sequence: Number(v) })} /></div>}
        onSave={() => confirmSave('grade-levels', grade, () => setGrade({ id: null, name: '', sequence: 0, active: true }), 'Grade Level')}
        onCancel={() => setGrade({ id: null, name: '', sequence: 0, active: true })}
        isEditing={Boolean(grade.id)}
      />

      <AcademicCard
        title="Sections" eyebrow="Class sections and adviser assignment"
        columns={[{ key: 'grade', label: 'Grade' }, { key: 'name', label: 'Section' }, { key: 'adviser_name', label: 'Adviser', render: (v) => v || <span style={{ color: 'var(--text-muted, #888)' }}>Unassigned</span> }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.sections}
        onEdit={(item) => setSection({ ...item, adviser_user_id: item.adviser_user_id || '' })}
        onDelete={(item) => confirmDelete('sections', item, `Section ${item.grade} - ${item.name}`)}
        extraActions={(item) => <button onClick={() => openAdviserModal(item)}><UserCheck size={14} /> Assign adviser</button>}
        form={<div className="form-grid three-columns"><label><span className="field-label">Grade Level</span><select className="input-field" value={section.grade_level_id} onChange={(e) => setSection({ ...section, grade_level_id: Number(e.target.value) })}>{structure.grade_levels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><Field label="Section name" value={section.name} onChange={(v) => setSection({ ...section, name: v })} /><label><span className="field-label">Adviser account</span><select className="input-field" value={section.adviser_user_id || ''} onChange={(e) => setSection({ ...section, adviser_user_id: e.target.value ? Number(e.target.value) : null })}><option value="">Unassigned</option>{teachers.map((item) => <option key={item.id} value={item.id}>{item.full_name} ({item.username})</option>)}</select></label></div>}
        formNote="Teacher access is linked to the adviser account ID. Use 'Assign adviser' from the Manage menu to re-route a teacher who resigned or changed classes without editing other section details."
        onSave={() => confirmSave('sections', section, () => setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', active: true }), 'Section')}
        onCancel={() => setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', active: true })}
        isEditing={Boolean(section.id)}
      />

      <AcademicCard
        title="Subjects" eyebrow="Learning areas"
        columns={[{ key: 'code', label: 'Code' }, { key: 'name', label: 'Subject Name' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.subjects}
        onEdit={(item) => setSubject({ ...item })}
        onDelete={(item) => confirmDelete('subjects', item, 'Subject')}
        form={<div className="form-grid two-columns"><Field label="Subject code (e.g. ENG)" value={subject.code} onChange={(v) => setSubject({ ...subject, code: v })} /><Field label="Subject name" value={subject.name} onChange={(v) => setSubject({ ...subject, name: v })} /></div>}
        onSave={() => confirmSave('subjects', subject, () => setSubject({ id: null, code: '', name: '', active: true }), 'Subject')}
        onCancel={() => setSubject({ id: null, code: '', name: '', active: true })}
        isEditing={Boolean(subject.id)}
      />

      {/* Adviser Reassignment Modal */}
      {adviserModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <div><p className="eyebrow">Section adviser management</p><h2>Assign Adviser — Grade {adviserModal.grade} · {adviserModal.name}</h2></div>
              <UserCheck size={24} />
            </div>
            <p className="section-copy">Reassigning an adviser immediately changes which teacher has access to this section. Use this when a teacher resigns, transfers, or swaps advisory classes in real life.</p>
            {adviserModal.adviser_name && <div className="notice notice-warning" style={{ marginBottom: '1rem' }}>Current adviser: <strong>{adviserModal.adviser_name}</strong></div>}
            <label>
              <span className="field-label">New adviser account</span>
              <select className="input-field" value={newAdviserId} onChange={(e) => setNewAdviserId(e.target.value)}>
                <option value="">Unassigned (remove adviser)</option>
                {teachers.map((t) => <option key={t.id} value={t.id}>{t.full_name} ({t.username})</option>)}
              </select>
            </label>
            <div className="modal-actions" style={{ marginTop: '1rem' }}>
              <button type="button" className="btn-secondary" onClick={() => setAdviserModal(null)}>Cancel</button>
              <button type="button" className="btn-primary" onClick={saveAdviser}><UserCheck size={16} /> Save Assignment</button>
            </div>
          </div>
        </div>
      )}

      {/* Global Confirmation Modal */}
      {confirm && <ConfirmModal title={confirm.title} message={confirm.message} danger={confirm.danger} onConfirm={confirm.onConfirm} onCancel={() => setConfirm(null)} />}
    </div>
  );
}

// ─── Roster Manager ─────────────────────────────────────────────────────────
function RosterManager({ imports, reload, success, fail }) {
  const [file, setFile] = useState(null); const [reference, setReference] = useState(''); const [preview, setPreview] = useState(null);
  const run = async (dryRun) => { if (!file) return fail(new Error('Select an approved .xlsx roster.')); const form = new FormData(); form.append('file', file); form.append('approved_reference', reference); form.append('dry_run', String(dryRun)); try { const result = await api.post('/admin/roster/import', form); setPreview(result); if (!dryRun) { success(`Roster imported: ${result.inserted} inserted and ${result.updated} updated.`); await reload(); } } catch (err) { fail(err); } };
  return (
    <div className="page-stack">
      <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Approved spreadsheet workflow</p><h2>Bulk roster import</h2></div><FileUp size={26} /></div><p className="section-copy">Required columns: External ID, Full Name, Sex, and Role. Students also require Grade and Section. Optional columns are LRN, Assignment, and Guardian Phone. Existing records with the same ID or LRN are updated.</p><div className="form-grid two-columns"><label><span className="field-label">Approved .xlsx roster</span><input className="input-field" type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); }} /></label><Field label="School approval / source reference" value={reference} onChange={setReference} required /></div><div className="modal-actions"><button className="btn-secondary" onClick={() => run(true)}><FileUp size={16} /> Validate preview</button><button className="btn-primary" disabled={!preview?.dry_run || preview.invalid_rows > 0} onClick={() => run(false)}><Plus size={16} /> Import valid roster</button></div>{preview && <div className={`notice ${preview.invalid_rows ? 'notice-danger' : 'notice-success'}`}>Valid rows: {preview.valid_rows ?? preview.inserted + preview.updated}. Invalid rows: {preview.invalid_rows}. {preview.errors?.slice(0, 8).map((item) => `Row ${item.row}: ${item.errors.join(', ')}`).join(' · ')}</div>}</section>
      <section className="card-static"><h2>Roster import audit</h2><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Imported</th><th>File</th><th>Approval</th><th>Counts</th><th>Actor</th><th>SHA-256</th></tr></thead><tbody>{imports.length === 0 && <tr><td colSpan="6" className="empty-cell">No approved roster has been imported.</td></tr>}{imports.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}</td><td>{item.filename}</td><td>{item.approved_reference}</td><td>{item.inserted_count} added, {item.updated_count} updated</td><td>{item.actor_name}</td><td className="model-version">{item.file_sha256}</td></tr>)}</tbody></table></div></section>
    </div>
  );
}

// ─── Recovery Manager ───────────────────────────────────────────────────────
function RecoveryManager({ backups, reload, success, fail }) {
  const [passphrase, setPassphrase] = useState(''); const [restoreFile, setRestoreFile] = useState(null); const [restorePassphrase, setRestorePassphrase] = useState(''); const [confirmation, setConfirmation] = useState('');
  const create  = async () => { const form = new FormData(); form.append('passphrase', passphrase); try { const result = await api.post('/admin/backups', form); setPassphrase(''); success(`Encrypted ${result.database_backend} backup ${result.filename} created.`); await reload(); } catch (err) { fail(err); } };
  const restore = async () => { if (!restoreFile) return fail(new Error('Select an .edubak recovery file.')); const form = new FormData(); form.append('file', restoreFile); form.append('passphrase', restorePassphrase); form.append('confirmation', confirmation); try { const result = await api.post('/admin/backups/restore', form); setRestorePassphrase(''); setConfirmation(''); success(result.offline_restore_required ? `Backup integrity verified (${result.file_count} files). Stop EduScan, then run ${result.apply_command} from the project folder.` : `Backup integrity verified (${result.file_count} files). Restart EduScan to apply it.`); } catch (err) { fail(err); } };
  return (
    <div className="page-stack">
      <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Database, encryption keys, faces, models, templates</p><h2>Create encrypted backup</h2></div><Database size={25} /></div><div className="notice notice-warning"><KeyRound size={18} /> The passphrase is not stored. Keep it in the school's approved password vault and retain an off-device copy of the .edubak file.</div><div className="form-grid two-columns"><Field label="Backup passphrase (at least 12 characters)" type="password" value={passphrase} onChange={setPassphrase} /><div className="modal-actions"><button className="btn-primary" onClick={create}><Database size={16} /> Create secure backup</button></div></div><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Created</th><th>Filename</th><th>Size</th><th /></tr></thead><tbody>{backups.length === 0 && <tr><td colSpan="4" className="empty-cell">No secure backup has been created.</td></tr>}{backups.map((item) => <tr key={item.filename}><td>{new Date(item.created_at).toLocaleString('en-PH')}</td><td>{item.filename}</td><td>{(item.size_bytes / 1024 / 1024).toFixed(2)} MB</td><td><button className="btn-link" onClick={() => api.download(`/admin/backups/${encodeURIComponent(item.filename)}`, item.filename).catch(fail)}><Download size={15} /> Download</button></td></tr>)}</tbody></table></div></section>
      <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Controlled two-stage recovery</p><h2>Verify and stage a restore</h2></div><ArchiveRestore size={25} /></div><p className="section-copy">The server decrypts and verifies every file hash before staging. SQLite applies on restart. MySQL requires the API to be stopped and the controlled PowerShell restore command to be run; that command first creates a fresh encrypted safety backup, imports the SQL, and then swaps the matching encryption artifacts.</p><div className="form-grid three-columns"><label><span className="field-label">EduScan .edubak file</span><input className="input-field" type="file" accept=".edubak" onChange={(e) => setRestoreFile(e.target.files?.[0] || null)} /></label><Field label="Backup passphrase" type="password" value={restorePassphrase} onChange={setRestorePassphrase} /><Field label='Type "STAGE RESTORE"' value={confirmation} onChange={setConfirmation} /></div><div className="modal-actions"><button className="btn-danger" onClick={restore}><ArchiveRestore size={16} /> Verify and stage restore</button></div></section>
    </div>
  );
}
