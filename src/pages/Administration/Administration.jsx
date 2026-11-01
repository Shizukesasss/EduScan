import usePagination from '../../hooks/usePagination';
import Pagination from '../../components/Common/Pagination';
import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle2, ChevronDown,
  Database, Pencil, Save,
  ShieldAlert, Trash2, UserCog, Users, UserCheck
} from 'lucide-react';
import { api, auth } from '../../api/client';
import OperationalControls from '../Operations/OperationalControls';
import { availableOptionId, isJuniorHighGrade, isSeniorHighGrade, subjectMatchesGrade } from '../../services/academicContext';
import { useToast } from '../../contexts/useToast';
import BiometricConsent from '../../components/Scanner/BiometricConsent';
import EnrollmentFields from '../../components/Scanner/EnrollmentFields';
import PhoneNumberField from '../../components/Scanner/PhoneNumberField';

const tabs = [
  ['accounts', 'Accounts'],
  ['people', 'People & records'],
  ['academic', 'School years & classes'],
];
const emptyPerson = {
  external_id: '', lrn: '', surname: '', first_name: '', middle_name: '', name_extension: '', sex: 'Female', role: 'Student', date_of_birth: '',
  grade: '', section: '', school_year_id: '', guardian_phone: '',
  enrollment_status: 'Regular', enrollment_note: '', enrollment_start_date: '', enrollment_end_date: '',
  transfer_school: '', biometric_consent: false,
};
const emptyUser = { username: '', password: '', role: 'teacher', full_name: '', active: true };
const SHS_TRACKS = ['Academic Track', 'Technical Professional (TechPro) Track'];
const SHS_TRACK_CLUSTERS = {
  'Academic Track': [
    'Arts, Social Sciences, and Humanities',
    'Science, Technology, Engineering, and Mathematics (STEM)',
    'Sports, Health, and Wellness',
    'Business and Entrepreneurship',
    'Field Experience',
  ],
  'Technical Professional (TechPro) Track': [
    'Aesthetic, Wellness, and Human Care',
    'Agri-Fishery Business and Food Innovation',
    'Artisanry and Creative Enterprise',
    'Automotive and Small Engine Technologies',
    'Construction and Building Technologies',
    'Creative Arts and Design Technologies',
    'Hospitality and Tourism',
    'ICT Support and Computer Programming Technologies',
    'Industrial Technologies',
    'Maritime',
  ],
};
const compareText = (left, right) => String(left ?? '').localeCompare(String(right ?? ''), undefined, { numeric: true, sensitivity: 'base' });
const orderedOptions = (items, getLabel = (item) => item?.name) => [...items].sort((a, b) => compareText(getLabel(a), getLabel(b)));
const orderedSections = (items) => [...items].sort((a, b) => compareText(a.grade, b.grade) || compareText(a.name, b.name));
const orderedTracks = orderedOptions(SHS_TRACKS, (track) => track);
const orderedElectiveTracks = orderedTracks;
const JHS_PROGRAMS = orderedOptions(['BEP', 'STE'], (program) => program);
const JHS_SUBJECT_CATALOG = [
  { code: 'AP', name: 'ARALING PANLIPUNAN', aliases: ['AP'] },
  { code: 'SCI', name: 'SCIENCE' },
  { code: 'VE', name: 'VALUES EDUCATION', aliases: ['VE'] },
  { code: 'FIL', name: 'FILIPINO' },
  { code: 'MATH', name: 'MATHEMATICS', aliases: ['MATH'] },
  { code: 'MAP', name: 'MAPEH' },
  { code: 'TLE', name: 'TECHNOLOGY AND LIVELIHOOD EDUCATION', aliases: ['TLE'] },
  { code: 'ENG', name: 'ENGLISH' },
];
const SHS_CORE_SUBJECT_CATALOG = [
  { code: 'SHS-CORE-EC', name: 'EFFECTIVE COMMUNICATION / MABISANG KOMUNIKASYON' },
  { code: 'SHS-CORE-GM', name: 'GENERAL MATHEMATICS' },
  { code: 'SHS-CORE-GS', name: 'GENERAL SCIENCE' },
  { code: 'SHS-CORE-LCS', name: 'LIFE AND CAREER SKILLS' },
  { code: 'SHS-CORE-PKLP', name: 'PAG-AARAL NG KASAYSAYAN AT LIPUNANG PILIPINO' },
];
const normalizeSubjectName = (name) => String(name || '').trim().replace(/\s+/g, ' ').toUpperCase();
const SHS_ELECTIVE_SUBJECT_CATALOG = {
  'Academic Track': {
    'Arts, Social Sciences, and Humanities': [
      'ART CRITICISM AND CREATIVE MARKETS',
      'CITIZENSHIP AND CIVIC ENGAGEMENT',
      'CONTEMPORARY LITERATURE 1',
      'CONTEMPORARY LITERATURE 2',
      'CREATIVE COMPOSITION 1',
      'CREATIVE COMPOSITION 2',
      'CREATIVE INDUSTRIES - APPLIED AND TRADITIONAL ARTS',
      'CREATIVE INDUSTRIES - DANCE',
      'CREATIVE INDUSTRIES - LITERARY ARTS',
      'CREATIVE INDUSTRIES - MEDIA ARTS',
      'CREATIVE INDUSTRIES - MUSIC',
      'CREATIVE INDUSTRIES - THEATER ARTS',
      'CREATIVE INDUSTRIES - VISUAL ARTS',
      'CREATIVE PRODUCTION AND PRESENTATION',
      'FILIPINO 1 - WIKA AT KOMUNIKASYON SA AKADEMIKONG FILIPINO',
      'FILIPINO 2 - FILIPINO PARA SA LARANG TEKNIKAL PROPESYONAL',
      'FILIPINO 2 - FILIPINO PARA SA ISPORTS',
      'FILIPINO 2 - FILIPINO SA SINING AT DISENYO',
      'FILIPINO IDENTITY THROUGH THE ARTS',
      'INTRODUCTION TO PHILOSOPHY',
      'LEADERSHIP AND MANAGEMENT IN THE ARTS',
      'MALIKHAING PAGSULAT',
      'PERFORMANCE CRITICISM AND CREATIVE MARKETS',
      'PHILIPPINE GOVERNANCE (PHILIPPINE POLITICS AND GOVERNANCE)',
      'SOCIAL SCIENCES (THEORY AND PRACTICE)',
    ],
    'Science, Technology, Engineering, and Mathematics (STEM)': [
      'ADVANCED MATHEMATICS',
      'BASIC CALCULUS',
      'BIOLOGY 1',
      'BIOLOGY 2',
      'BIOLOGY 3',
      'BIOLOGY 4',
      'CHEMISTRY 1',
      'CHEMISTRY 2',
      'CHEMISTRY 3',
      'CHEMISTRY 4',
      'CONCEPTUAL BIOLOGY AND EARTH AND SPACE SCIENCE',
      'CONCEPTUAL PHYSICS AND CHEMISTRY IN DAILY LIFE',
      'DATABASE MANAGEMENT',
      'EARTH AND SPACE SCIENCE 1',
      'EARTH AND SPACE SCIENCE 2',
      'EARTH AND SPACE SCIENCE 3',
      'EARTH AND SPACE SCIENCE 4',
      'EMPOWERMENT TECHNOLOGIES',
      'FINITE MATHEMATICS 1',
      'FINITE MATHEMATICS 2',
      'FUNDAMENTALS OF DATA ANALYTICS',
      'PHYSICS 1',
      'PHYSICS 2',
      'PHYSICS 3',
      'PHYSICS 4',
      'PRE-CALCULUS',
    ],
    'Sports, Health, and Wellness': [
      'EXERCISE AND SPORTS PROGRAMMING',
      'FIRST AID',
      'FUNDAMENTALS OF BASIC LIFE SUPPORT',
      'HUMAN MOVEMENT 1 - BASIC ANATOMY IN SPORTS AND EXERCISE',
      'HUMAN MOVEMENT 2 - MOTOR SKILLS DEVELOPMENT',
      'PHYSICAL EDUCATION 1 - FITNESS AND RECREATION',
      'PHYSICAL EDUCATION 2 - SPORTS AND DANCE',
      'SPORTS ACTIVITY MANAGEMENT',
      'SPORTS COACHING',
      'SPORTS OFFICIATING',
    ],
    'Business and Entrepreneurship': [
      'BUSINESS 1 - BASIC ACCOUNTING',
      'BUSINESS 2 - BUSINESS FINANCE AND INCOME TAXATION',
      'BUSINESS 3 - BUSINESS ECONOMICS',
      'CONTEMPORARY MARKETING',
      'ENTREPRENEURSHIP',
      'INTRODUCTION TO ORGANIZATION AND MANAGEMENT',
    ],
    'Field Experience': [
      'ARTS APPRENTICESHIP – DANCE',
      'ARTS APPRENTICESHIP – LITERARY ARTS',
      'ARTS APPRENTICESHIP – MEDIA ARTS',
      'ARTS APPRENTICESHIP – MUSIC',
      'ARTS APPRENTICESHIP – THEATER ARTS',
      'ARTS APPRENTICESHIP – TRADITIONAL CULTURAL EXPRESSIONS',
      'ARTS APPRENTICESHIP – VISUAL ARTS',
      'DESIGN AND INNOVATION',
      'FIELD EXPOSURE (OFF-CAMPUS)',
      'IN-CAMPUS FIELD EXPOSURE FOR SPORTS',
      'RESEARCH 1',
      'RESEARCH 2',
    ],
  },
  'Technical Professional (TechPro) Track': {
    'Aesthetic, Wellness, and Human Care': [
      'AESTHETIC SERVICES (BEAUTY CARE)',
      'CAREGIVING (ADULT CARE)',
      'CAREGIVING (CHILD CARE)',
      'HAIRDRESSING SERVICES',
    ],
    'Agri-Fishery Business and Food Innovation': [
      'AGRICULTURAL-CROPS-PRODUCTION',
      'AGRO-ENTREPRENEURSHIP',
      'AQUACULTURE',
      'FISH-CAPTURE',
      'FOOD-PROCESSING',
      'ORGANIC-AGRICULTURE-PRODUCTION',
      'POULTRY-PRODUCTION-CHICKEN',
      'RUMINANTS-PRODUCTION',
      'SWINE-PRODUCTION',
    ],
    'Artisanry and Creative Enterprise': [
      'GARMENTS ARTISANRY',
      'HANDICRAFTS (WEAVING)',
    ],
    'Automotive and Small Engine Technologies': [
      'AUTOMOTIVE SERVICING (ELECTRICAL REPAIR)',
      'AUTOMOTIVE SERVICING (ENGINE AND CHASSIS REPAIRS)',
      'DRIVING AND AUTOMOTIVE SERVICING',
      'MOTORCYCLE AND SMALL ENGINE SERVICING',
    ],
    'Construction and Building Technologies': [
      'CARPENTRY',
      'CONSTRUCTION OPERATION',
      'MANUAL METAL ARC WELDING',
      'TECHNICAL DRAFTING',
    ],
    'Creative Arts and Design Technologies': [
      'ANIMATION',
      'ILLUSTRATION',
      'VISUAL GRAPHIC DESIGN',
    ],
    'Hospitality and Tourism': [
      'BAKERY OPERATIONS',
      'EVENTS MANAGEMENT SERVICES',
      'FOOD AND BEVERAGE OPERATION',
      'HOTEL OPERATION (FRONT OFFICE SERVICES)',
      'HOTEL OPERATION (HOUSEKEEPING SERVICES)',
      'KITCHEN OPERATIONS',
      'TOURISM SERVICES',
    ],
    'ICT Support and Computer Programming Technologies': [
      'BROADBAND INSTALLATION',
      'COMPUTER PROGRAMMING (.NET TECHNOLOGY)',
      'COMPUTER PROGRAMMING (JAVA)',
      'COMPUTER PROGRAMMING (ORACLE DATABASE)',
      'COMPUTER SYSTEMS SERVICING',
      'CONTACT CENTER SERVICES',
    ],
    'Industrial Technologies': [
      'COMMERCIAL AIR CONDITIONING INSTALLATION AND SERVICING',
      'DOMESTIC REFRIGERATION AND AIR CONDITIONING SERVICING',
      'ELECTRICAL INSTALLATION AND MAINTENANCE',
      'ELECTRONIC PRODUCTS ASSEMBLY AND SERVICING',
      'MECHATRONICS',
      'PHOTOVOLTAIC SYSTEMS INSTALLATION',
    ],
    'Maritime': [
      'MARINE ENGINEERING AT THE SUPPORT LEVEL',
      'MARINE TRANSPORTATION AT THE SUPPORT LEVEL',
      'SHIPS CATERING SERVICES',
    ],
  },
};
const jhsCatalogSubject = (subject) => {
  const name = String(subject?.name || '').trim().toUpperCase();
  const code = String(subject?.code || '').trim().toUpperCase();
  const byName = JHS_SUBJECT_CATALOG.find(item => item.name === name || (item.aliases || []).includes(name));
  const byCode = JHS_SUBJECT_CATALOG.find(item => item.code === code || (item.aliases || []).includes(code));
  if (name && !byName) return undefined;
  return byName && byCode && byName.code !== byCode.code ? undefined : byName || byCode;
};
const shsCoreCatalogSubject = (subject) => {
  const name = normalizeSubjectName(subject?.name);
  const code = String(subject?.code || '').trim().toUpperCase();
  const byName = SHS_CORE_SUBJECT_CATALOG.find(item => item.name === name);
  const byCode = SHS_CORE_SUBJECT_CATALOG.find(item => item.code === code);
  if (name && !byName) return undefined;
  return byName && byCode && byName.code !== byCode.code ? undefined : byName || byCode;
};
const personNamePattern = "[\\p{L}\\p{M} '’.-]+";

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
function Field({ label, value, onChange, type = 'text', required = false, disabled = false, pattern, title }) {
  return (
    <label>
      <span className="field-label">{label}</span>
      <input placeholder={String(label).startsWith('Type') ? label : `Enter ${String(label).toLowerCase()}`} className="input-field" type={type} value={value ?? ''} onChange={(e) => onChange(e.target.value)} required={required} disabled={disabled} pattern={pattern} title={title} />
    </label>
  );
}
function SectionAssignmentPicker({ sections, selectedIds, onChange }) {
  const paging = usePagination(sections, sections.map(item => `${item.grade}:${item.track || ''}:${item.track_cluster || ''}`).filter((item,index,array) => array.indexOf(item) === index).join('|'));
  const selected = new Set(selectedIds.map(Number));
  const toggle = (sectionId) => {
    const next = new Set(selected);
    if (next.has(sectionId)) next.delete(sectionId);
    else next.add(sectionId);
    onChange([...next]);
  };

  return (
    <fieldset className="assignment-section-picker">
      <legend className="field-label">Sections</legend>
      <div className="assignment-section-picker-header">
        <span>{selected.size} of {sections.length} sections selected</span>
        <div>
          <button type="button" className="btn-link" onClick={() => onChange(sections.map((item) => item.id))} disabled={!sections.length}>Select all</button>
          <button type="button" className="btn-link" onClick={() => onChange([])} disabled={!selected.size}>Clear</button>
        </div>
      </div>
      {sections.length ? (
        <div className="assignment-section-list">
          {paging.items.map((item) => (
            <label className="assignment-section-option" key={item.id}>
              <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
              <span>
                <strong>Grade {item.grade} · Section {item.name}</strong>
                {item.track && <small>{item.track}</small>}
                {item.track_cluster && <small>{item.track_cluster}</small>}
                {item.assigned_teacher_name && <small>Currently assigned to {item.assigned_teacher_name}</small>}
              </span>
            </label>
          ))}
        </div>
      ) : <p className="section-copy assignment-section-empty">No active sections match this subject’s grade level or track.</p>}
      <Pagination {...paging} label="sections" />
    </fieldset>
  );
}
function SelectField({ label, value, onChange, options }) {
  const values = options.includes('admin')
    ? [...new Set([...options, 'records_officer', 'privacy_officer', 'ict', 'school_head'])]
    : options;
  const sortedValues = [...values.filter((option) => option === ''), ...orderedOptions(values.filter((option) => option !== ''), (option) => option)];
  return (
    <label>
      <span className="field-label">{label}</span>
      <select className="input-field" value={value} onChange={(e) => onChange(e.target.value)}>
        {sortedValues.map((option) => <option key={option} value={option}>{option === 'school_head' ? 'School head (read-only)' : option}</option>)}
      </select>
    </label>
  );
}

export default function Administration() {
  const role = auth.role();
  const [searchParams, setSearchParams] = useSearchParams();
  const available = [
    ...(role === 'admin' ? tabs : []),
    ...(['admin', 'records_officer', 'privacy_officer'].includes(role) ? [['activity', 'Activity']] : []),
    ...(['admin', 'privacy_officer'].includes(role) ? [['data', 'Data management']] : []),
    ...(['admin', 'ict'].includes(role) ? [['backup', 'Backup & recovery']] : []),
    ...(role === 'ict' ? [['health', 'Service health']] : []),
  ];
  const requestedTab = searchParams.get('tab');
  const active = available.some(([id]) => id === requestedTab) ? requestedTab : available[0]?.[0] || 'activity';
  return <div className="page-stack">
    <div className="setup-tabs">{available.map(([id, label]) =>
      <button key={id} className={active === id ? 'active' : ''} onClick={() => setSearchParams({ tab: id })}>{label}</button>)}</div>
    {tabs.some(([id]) => id === active) && role === 'admin' && <AdminRecords active={active} />}
    {['activity', 'data', 'backup', 'health'].includes(active) && <OperationalControls view={active} />}
  </div>;
}

// Only the active records tab loads administrator-only data.
function AdminRecords({ active }) {
  const [people, setPeople] = useState([]);
  const [users, setUsers] = useState([]);
  const [structure, setStructure] = useState({ school_years: [], grading_periods: [], grade_levels: [], sections: [], subjects: [] });
  const [disposals, setDisposals] = useState([]);
  const [deletedReferences, setDeletedReferences] = useState([]);
  const { showSuccess, showError } = useToast();

  const load = useCallback(() => {
    const paths = {
      people: ['/admin/persons', '/admin/academic-structure', '/admin/disposals'],
      accounts: ['/admin/users', '/admin/academic-structure'],
      academic: ['/admin/academic-structure', '/admin/users', '/admin/reference-deleted'],
    };
    return Promise.all(paths[active].map((path) => api.get(path))).then((rows) => {
      if (active === 'people') { setPeople(rows[0]); setStructure(rows[1]); setDisposals(rows[2]); }
      else if (active === 'accounts') { setUsers(rows[0]); setStructure(rows[1]); }
      else if (active === 'academic') { setStructure(rows[0]); setUsers(rows[1]); setDeletedReferences(rows[2]); }
    }).catch((err) => showError(err.message));
  }, [active, showError]);

  useEffect(() => { load(); }, [load]);
  const success = (msg) => showSuccess(msg);
  const fail    = (err) => showError(err.message);

  return (
    <div className="page-stack">
      {active === 'people'   && <PeopleManager people={people} disposals={disposals} reload={load} success={success} fail={fail} structure={structure} />}
      {active === 'accounts' && <AccountManager users={users} schoolYears={structure.school_years} reload={load} success={success} fail={fail} />}
      {active === 'academic' && <AcademicManager structure={structure} deletedReferences={deletedReferences} teachers={users.filter((u) => u.role === 'teacher' && u.active)} reload={load} success={success} fail={fail} />}
    </div>
  );
}

// ─── People Manager ─────────────────────────────────────────────────────────
function PeopleManager({ people, disposals, reload, success, fail, structure }) {
  const [form, setForm] = useState(emptyPerson);
  const [editing, setEditing] = useState(null);
  const [disposal, setDisposal] = useState(null);
  const editingRole = people.find((item) => item.id === editing)?.role;
  const patch = (field, value) => setForm((c) => ({ ...c, [field]: value, ...(field === 'role' && value !== c.role ? { enrollment_status: value === 'Student' ? 'Regular' : 'Appointed', enrollment_end_date: '', school_year_id: '' } : {}) }));
  const edit  = (item) => { setEditing(item.id); setForm(Object.fromEntries(Object.keys(emptyPerson).map((k) => [k, item[k] ?? emptyPerson[k]]))); };
  const save  = async (event) => {
    event.preventDefault();
    try {
      const payload = { ...form, external_id: form.role === 'Student' && !editing ? form.lrn : form.external_id, lrn: form.role === 'Student' ? form.lrn || null : null, date_of_birth: form.date_of_birth || null, middle_name: form.middle_name || null, name_extension: form.name_extension || null, grade: form.grade || null, section: form.section || null, guardian_phone: form.guardian_phone || null, enrollment_note: form.enrollment_note || null, enrollment_start_date: form.enrollment_start_date || null, enrollment_end_date: form.enrollment_end_date || null, transfer_school: form.transfer_school || null };
      if (editing || form.role !== 'Student') delete payload.school_year_id;
      else payload.school_year_id = Number(form.school_year_id);
      if (editing) await api.patch(`/persons/${editing}`, payload); else await api.post('/persons', payload);
      success(editing ? 'School record updated.' : 'School record created.'); setEditing(null); setForm(emptyPerson); await reload();
    } catch (err) { fail(err); }
  };
  const setActive = async (item) => { const data = new FormData(); data.append('active', String(!item.active)); try { await api.post(`/admin/persons/${item.id}/active`, data); success(`${item.full_name} ${item.active ? 'deactivated' : 'reactivated'}.`); await reload(); } catch (err) { fail(err); } };
  return (
    <div className="page-stack">
      <div className="notice notice-blue">Create or update a school record here when camera capture is unavailable. This does not enroll a face. To capture face samples and train the model, use <a href="/scanner">Gate Station → Enroll person</a>. Staff can record a verified assisted visit in Attendance.</div>
      <section className="card-static">
        <div className="section-heading"><div><p className="eyebrow">Students, faculty, and personnel</p><h2>{editing ? 'Edit school record' : 'Add school record'}</h2></div><Users size={24} /></div>
        <form onSubmit={save}>
          <div className="form-grid three-columns">
            {form.role === 'Student'
              ? <Field label="LRN" value={form.lrn} onChange={(v) => patch('lrn', v)} required />
              : <Field label="Employee ID" value={form.external_id} onChange={(v) => patch('external_id', v)} required />}
            <SelectField label="Role" value={form.role} onChange={(v) => patch('role', v)} options={['Student', 'Faculty', 'Non-teaching Personnel']} />
            <Field label="Surname" value={form.surname} onChange={(v) => patch('surname', v)} required pattern={personNamePattern} title="Use letters and common name punctuation only." />
            <Field label="First name" value={form.first_name} onChange={(v) => patch('first_name', v)} required pattern={personNamePattern} title="Use letters and common name punctuation only." />
            <Field label="Middle name" value={form.middle_name} onChange={(v) => patch('middle_name', v)} pattern={personNamePattern} title="Use letters and common name punctuation only." />
            <Field label="Extension (e.g. Jr.)" value={form.name_extension} onChange={(v) => patch('name_extension', v)} pattern={personNamePattern} title="Use letters and common name punctuation only." />
            <SelectField label="Sex for SF2" value={form.sex} onChange={(v) => patch('sex', v)} options={['Female', 'Male']} />
            <PhoneNumberField label={form.role === 'Student' ? 'Guardian phone' : 'Phone number'} value={form.guardian_phone} onChange={(v) => patch('guardian_phone', v)} />
            {form.role === 'Student' && (
              <>
                {!editing && <label><span className="field-label">School year placement</span><select className="input-field" value={form.school_year_id} onChange={(event) => patch('school_year_id', event.target.value)} required><option value="">Choose school year</option>{orderedOptions(structure.school_years).map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>}
                <SelectField label="Grade level" value={form.grade} onChange={(v) => { patch('grade', v); patch('section', ''); }} options={['', ...orderedOptions(structure.grade_levels.filter((g) => g.active)).map((g) => g.name)]} />
                <SelectField label="Section" value={form.section} onChange={(v) => patch('section', v)} options={['', ...orderedOptions(structure.sections.filter(s => s.active && s.grade_level_id === structure.grade_levels.find(g => g.name === form.grade)?.id), (s) => s.name).map((s) => s.name)]} />
              </>
            )}
            <EnrollmentFields form={form} onChange={patch} dateOfBirthRequired={!editing || (form.role === 'Student' && editingRole !== 'Student')} enrollmentStartDateRequired={!editing} />
            <BiometricConsent checked={form.biometric_consent} onChange={(value) => patch('biometric_consent', value)} />
          </div>
          <div className="modal-actions">{editing && <button type="button" className="btn-secondary" onClick={() => { setEditing(null); setForm(emptyPerson); }}>Cancel</button>}<button className="btn-primary"><Save size={16} /> {editing ? 'Save changes' : 'Create record'}</button></div>
        </form>
      </section>
      <section className="card-static">
        <h2>School records</h2>
        <p className="section-copy">Students use an LRN; teaching and non-teaching staff use an employee ID. Deactivation preserves history and blocks recognition. Full disposal permanently removes the person, face enrollment, and linked records.</p>
        <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Name</th><th>ID / LRN</th><th>Role / placement</th><th>Movement</th><th>Status</th><th /></tr></thead><PaginatedBody>{people.map((item) => <tr key={item.id}><td><strong>{item.full_name}</strong>{item.possible_duplicate && <span className="table-subline duplicate-warning">Possible duplicate name—verify IDs</span>}</td><td>{item.role === 'Student' ? item.lrn || 'LRN not recorded' : item.external_id}<span className="table-subline">{item.role === 'Student' ? 'LRN' : 'Employee ID'}</span></td><td>{item.role}<span className="table-subline">{item.grade ? `Grade ${item.grade} — ${item.section}` : '—'}</span></td><td>{item.enrollment_status}{item.transfer_school && <span className="table-subline">{item.transfer_school}</span>}{item.enrollment_end_date && <span className="table-subline">Last day: {item.enrollment_end_date}</span>}{item.enrollment_note && <span className="table-subline">{item.enrollment_note}</span>}</td><td><span className={`tag ${item.active ? 'tag-success' : 'tag-gray'}`}>{item.active ? 'Active' : 'Inactive'}</span></td><td><details className="action-menu table-action-menu"><summary><ChevronDown size={15} /> Manage</summary><div className="action-menu-panel"><button onClick={() => edit(item)}><Pencil size={14} /> Edit record</button><button onClick={() => setActive(item)}>{item.active ? 'Deactivate record' : 'Reactivate record'}</button><button className="danger-link" onClick={() => setDisposal(item)}><Trash2 size={14} /> Full disposal</button></div></details></td></tr>)}</PaginatedBody></table></div>
      </section>
      <section className="card-static"><h2>Record-disposal audit</h2><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Completed</th><th>Anonymous reference</th><th>Authority</th><th>Reason</th><th>Removed</th><th>Actor</th></tr></thead><PaginatedBody>{disposals.length === 0 && <tr><td colSpan="6" className="empty-cell">No full record disposal has been performed.</td></tr>}{disposals.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}</td><td>{item.disposal_reference}</td><td>{item.authorization_reference}</td><td>{item.reason}</td><td>{Object.entries(item.removed_counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</td><td>{item.actor_name}</td></tr>)}</PaginatedBody></table></div></section>
      {disposal && <DisposalModal person={disposal} onClose={() => setDisposal(null)} onDone={async (result) => { setDisposal(null); if (result.file_cleanup_pending) fail(new Error('The record and recognition enrollment were removed, but some encrypted files could not be deleted. Contact the administrator to complete file cleanup.')); else success('The selected person, face enrollment, and linked school records were disposed.'); await reload(); }} fail={fail} />}
    </div>
  );
}

function DisposalModal({ person, onClose, onDone, fail }) {
  const [confirmed, setConfirmed] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [saving, setSaving] = useState(false);
  const identifier = person.role === 'Student' ? person.lrn || person.external_id : person.external_id;
  const identifierLabel = person.role === 'Student' && person.lrn ? 'LRN' : 'school / employee ID';
  const submit = async (event) => {
    event.preventDefault();
    if (!confirmed || confirmation !== identifier || saving) return;
    setSaving(true);
    try { const result = await api.delete(`/admin/persons/${person.id}/records`, { confirmed, confirmation }); await onDone(result); }
    catch (err) { fail(err); setSaving(false); }
  };
  return <div className="modal-backdrop"><form className="modal-card" role="dialog" aria-modal="true" aria-labelledby="disposal-title" onSubmit={submit}>
    <div className="modal-header"><div><p className="eyebrow">Permanent disposal</p><h2 id="disposal-title">Delete all records for {person.full_name}</h2></div><ShieldAlert color="#dc2626" /></div>
    <div className="notice notice-danger">This permanently removes this person's school record, saved face samples and model membership, attendance, grades, SMS, and other linked records. This cannot be undone here. Deactivate the record instead if the person has left and their history must be kept.</div>
    <label className="checkbox-field"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} required /><span>I am authorized to permanently dispose of these records and understand that the face enrollment and linked records will be deleted.</span></label>
    <Field label={`Type the ${identifierLabel}: ${identifier}`} value={confirmation} onChange={setConfirmation} required />
    <div className="modal-actions"><button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button><button className="btn-danger" disabled={saving || !confirmed || confirmation !== identifier}><Trash2 size={16} /> {saving ? 'Disposing records...' : 'Permanently dispose records'}</button></div>
  </form></div>;
}

// ─── Account Manager ────────────────────────────────────────────────────────
function SchoolHeadSettings({ schoolYears, success, fail }) {
  const [assignments, setAssignments] = useState({});
  const [yearId, setYearId] = useState('');
  const selectedYearId = String(availableOptionId(schoolYears, yearId));
  const form = assignments[selectedYearId] || { full_name: '', title: 'Principal' };
  const updateForm = (field, value) => setAssignments((current) => ({ ...current, [selectedYearId]: { ...form, [field]: value } }));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { showError } = useToast();
  useEffect(() => {
    let cancelled = false;
    api.get('/admin/school-heads').then((data) => {
      if (cancelled) return;
      setAssignments(data);
    }).catch((error) => { if (!cancelled) showError(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [showError]);
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.put('/admin/school-heads', { school_year_id: Number(selectedYearId), ...form });
      success('School head saved for this school year. New class-record exports will include the name.');
    } catch (error) { fail(error); }
    finally { setSaving(false); }
  };
  return <section className="card-static">
    <div className="section-heading"><div><p className="eyebrow">Class-record export details</p><h2>School head</h2></div></div>
    <p className="section-copy">Assign the principal for each school year. Update this when the school head changes; other school years and previously downloaded files keep their existing details. Manage their login separately in Accounts below.</p>
    <form onSubmit={save}>
      <div className="form-grid three-columns">
        <label><span className="field-label">School year</span><select className="input-field" value={selectedYearId} disabled={loading || saving} onChange={(event) => setYearId(event.target.value)} required>{orderedOptions(schoolYears).map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
        <label><span className="field-label">School head full name</span><input placeholder="Enter school head full name" className="input-field" value={form.full_name} minLength={3} maxLength={160} disabled={loading || saving} onChange={(event) => updateForm('full_name', event.target.value)} required /></label>
        <label><span className="field-label">Official title</span><input placeholder="Enter official title" className="input-field" value={form.title} minLength={2} maxLength={100} disabled={loading || saving} onChange={(event) => updateForm('title', event.target.value)} required /></label>
      </div>
      <div className="modal-actions"><button className="btn-primary" disabled={loading || saving || !selectedYearId}>{saving ? 'Saving…' : 'Save school head'}</button></div>
    </form>
  </section>;
}

function AccountManager({ users, schoolYears, reload, success, fail }) {
  const [form, setForm] = useState(emptyUser); const [editing, setEditing] = useState(null);
  const patch = (field, value) => setForm((c) => ({ ...c, [field]: value }));
  const edit  = (item) => { setEditing(item.id); setForm({ username: item.username, password: '', role: item.role, full_name: item.full_name, active: item.active }); };
  const save  = async (event) => { event.preventDefault(); try { if (editing) await api.put(`/admin/users/${editing}`, { role: form.role, full_name: form.full_name, active: form.active, new_password: form.password || null }); else await api.post('/admin/users', form); success(editing ? 'Account updated.' : 'Account created.'); setEditing(null); setForm(emptyUser); await reload(); } catch (err) { fail(err); } };
  const deactivate    = async (item) => { try { await api.delete(`/admin/users/${item.id}`); success(`${item.username} was deactivated.`); await reload(); } catch (err) { fail(err); } };
  const unlock        = async (item) => { try { await api.post(`/admin/users/${item.id}/unlock`, {}); success(`${item.username} was unlocked.`); await reload(); } catch (err) { fail(err); } };
  return (
    <div className="page-stack">
      <SchoolHeadSettings schoolYears={schoolYears} success={success} fail={fail} />
      <section className="card-static">
        <div className="section-heading"><div><p className="eyebrow">Role-based access</p><h2>{editing ? 'Edit account' : 'Create account'}</h2></div><UserCog size={24} /></div>
        <p className="section-copy">Temporary and reset passwords need 12 or more characters, including a capital letter, a small letter, a number, and a symbol such as ! or #. The account owner must choose a new password the next time they sign in.</p>
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
        <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Security</th><th /></tr></thead><PaginatedBody>{users.map((item) => <tr key={item.id}><td>{item.full_name}{item.is_demo && <span className="table-subline">Demo account</span>}</td><td>{item.username}</td><td>{item.role}</td><td>{item.active ? 'Active' : 'Inactive'}</td><td>{item.locked_until ? `Locked until ${new Date(item.locked_until).toLocaleString('en-PH')}` : item.must_change_password ? 'Password change required' : 'Ready'}</td><td><details className="action-menu table-action-menu"><summary><ChevronDown size={15} /> Manage</summary><div className="action-menu-panel"><button onClick={() => edit(item)}><Pencil size={14} /> Edit account</button>{item.locked_until && <button onClick={() => unlock(item)}>Unlock account</button>}{item.active && item.username !== 'admin' && <button className="danger-link" onClick={() => deactivate(item)}>Deactivate account</button>}</div></details></td></tr>)}</PaginatedBody></table></div>
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
                <th key={col.key} style={{ userSelect: 'none', whiteSpace: 'nowrap' }}>
                  <span className="academic-sort-heading">
                    {col.label}
                    <button
                      type="button"
                      className={`academic-sort-button${sortKey === col.key ? ' is-sorted' : ''}`}
                      title={sortKey === col.key ? `Sorted ${sortDir === 'asc' ? 'ascending' : 'descending'}; click to reverse` : `Sort by ${col.label}`}
                      aria-label={sortKey === col.key ? `Sorted ${sortDir === 'asc' ? 'ascending' : 'descending'} by ${col.label}; click to reverse` : `Sort by ${col.label}`}
                      onClick={() => toggleSort(col.key)}
                    >
                      <svg className="sort-directions-icon" viewBox="0 0 28 24" aria-hidden="true" focusable="false">
                        <path d="M2 8 8 2l6 6M8 2v20M14 16l6 6 6-6M20 2v20" />
                      </svg>
                    </button>
                  </span>
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <PaginatedBody>
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
          </PaginatedBody>
        </table>
      </div>
    </section>
  );
}

// ─── Academic Manager ───────────────────────────────────────────────────────
function AcademicManager({ structure, deletedReferences, teachers, reload, success, fail }) {
  const sortedSchoolYears = orderedOptions(structure.school_years);
  const [adviserYear, setAdviserYear] = useState('');
  const adviserYearId = Number(adviserYear || sortedSchoolYears.find(year => year.active)?.id || 0);
  const yearlySections = structure.sections.map(section => {
    const assignment = (structure.adviser_assignments || []).find(item => item.school_year_id === adviserYearId && item.section_id === section.id);
    return { ...section, track_label: [section.track, section.track_cluster].filter(Boolean).join(' · '), adviser_user_id: assignment?.teacher_user_id || null, adviser_name: assignment?.adviser_name || null };
  });
  const sortedGradeLevels = orderedOptions(structure.grade_levels);
  const sortedSubjects = orderedOptions(structure.subjects, (item) => `${item.name} (${item.category})`);
  const sortedSections = orderedSections(structure.sections);
  const sortedTeachers = orderedOptions(teachers, (item) => `${item.full_name} ${item.username}`);
  const sortedTracks = orderedTracks;
  const sortedJhsPrograms = JHS_PROGRAMS;
  const firstYear  = sortedSchoolYears[0]?.id  || '';
  const firstGrade = sortedGradeLevels[0]?.id  || '';

  const [year,    setYear]    = useState({ id: null, name: '', starts_on: '', ends_on: '', active: true });
  const [period,  setPeriod]  = useState({ id: null, school_year_id: '', name: 'Term 1', starts_on: '', ends_on: '', active: true });
  const [grade,   setGrade]   = useState({ id: null, name: '', active: true });
  const [section, setSection] = useState({ id: null, grade_level_id: '', name: '', adviser_user_id: '', adviser_name: '', track: '', track_cluster: '', active: true });
  const [subject, setSubject] = useState({ id: null, code: '', name: '', category: 'JHS', is_elective: false, allowed_grades: [7, 8, 9, 10], elective_track: '', elective_cluster: '', active: true });
  const [teaching, setTeaching] = useState({ id: null, school_year_id: '', subject_id: '', teacher_user_id: '', section_ids: [] });
  const subjectIsShs = String(subject.category || 'JHS').toUpperCase().startsWith('SHS');
  const subjectIsShsElective = subjectIsShs && subject.is_elective;
  const subjectUsesJhsCatalog = !subjectIsShs && !subject.is_elective;
  const subjectUsesShsCoreCatalog = subjectIsShs && !subject.is_elective;
  const selectedJhsCatalogSubject = jhsCatalogSubject(subject);
  const selectedShsCoreSubject = shsCoreCatalogSubject(subject);
  const jhsCatalogOptions = JHS_SUBJECT_CATALOG.map(item => ({
    ...item,
    alreadyAdded: structure.subjects.some(existing => existing.id !== subject.id
      && !String(existing.category || 'JHS').toUpperCase().startsWith('SHS')
      && !existing.is_elective && jhsCatalogSubject(existing)?.code === item.code),
  }));
  const shsCoreCatalogOptions = SHS_CORE_SUBJECT_CATALOG.map(item => ({
    ...item,
    alreadyAdded: structure.subjects.some(existing => existing.id !== subject.id
      && String(existing.category || '').toUpperCase().startsWith('SHS')
      && (normalizeSubjectName(existing.name) === item.name || String(existing.code || '').trim().toUpperCase() === item.code)),
  }));
  const currentSubject = structure.subjects.find(item => Number(item.id) === Number(subject.id));
  const shsElectiveNames = SHS_ELECTIVE_SUBJECT_CATALOG[subject.elective_track]?.[subject.elective_cluster] || [];
  const shsElectiveOptions = [...new Set([
    ...shsElectiveNames,
    ...(subjectIsShsElective && currentSubject?.name ? [normalizeSubjectName(currentSubject.name)] : []),
  ])].map(name => {
    const existing = structure.subjects.find(item => String(item.category || '').toUpperCase().startsWith('SHS')
      && normalizeSubjectName(item.name) === name);
    return { name, alreadyAdded: Boolean(existing && existing.id !== subject.id), existing };
  });
  const selectedShsElectiveSubject = shsElectiveOptions.find(item => item.name === normalizeSubjectName(subject.name));

  const [adviserModal, setAdviserModal] = useState(null);
  const [newAdviserId, setNewAdviserId] = useState('');
  const [confirm, setConfirm] = useState(null);

  const periodYearId = availableOptionId(sortedSchoolYears, period.school_year_id);
  const sectionGradeId = availableOptionId(sortedGradeLevels, section.grade_level_id);
  const teachingYearId = availableOptionId(sortedSchoolYears, teaching.school_year_id);
  const teachingSubjectId = availableOptionId(sortedSubjects, teaching.subject_id);
  const selectedYearId = Number(teaching.school_year_id || teachingYearId);
  const selectedSubjectId = Number(teaching.subject_id || teachingSubjectId);
  const teachingSubject = sortedSubjects.find((item) => item.id === selectedSubjectId);
  const existingAssignmentsBySection = new Map((structure.subject_assignments || [])
    .filter((item) => item.school_year_id === selectedYearId && item.subject_id === selectedSubjectId)
    .map((item) => [item.section_id, item]));
  const eligibleTeachingSections = orderedSections(sortedSections.filter((item) => {
    if (!teachingSubject) return false;
    if (!item.active) return false;
    if (existingAssignmentsBySection.has(item.id)) return true;
    if (!subjectMatchesGrade(teachingSubject, item.grade)) return false;
    const sectionIsShs = isSeniorHighGrade(item.grade);
    if (sectionIsShs !== String(teachingSubject.category).toUpperCase().startsWith('SHS')) return false;
    const matchesTrack = !teachingSubject.is_elective || !teachingSubject.elective_track
      || item.track?.trim().toLowerCase() === teachingSubject.elective_track.trim().toLowerCase();
    const matchesCluster = !teachingSubject.elective_cluster
      || item.track_cluster?.trim().toLowerCase() === teachingSubject.elective_cluster.trim().toLowerCase();
    return matchesTrack && matchesCluster;
  })).map((item) => ({
    ...item,
    assigned_teacher_name: (existingAssignmentsBySection.get(item.id)?.teacher_name || '')
      + (!subjectMatchesGrade(teachingSubject, item.grade) ? ' — outside allowed grades; review required' : '')
      + (teachingSubject?.elective_cluster && item.track_cluster?.trim().toLowerCase() !== teachingSubject.elective_cluster.trim().toLowerCase() ? ' — different SHS cluster; review required' : ''),
  }));
  if (!period.id && period.school_year_id !== periodYearId) {
    setPeriod({ ...period, school_year_id: periodYearId });
  }
  if (!section.id && section.grade_level_id !== sectionGradeId) {
    setSection({ ...section, grade_level_id: sectionGradeId });
  }
  if ((!teaching.school_year_id && teachingYearId) || (!teaching.subject_id && teachingSubjectId)) {
    setTeaching({ ...teaching, school_year_id: teaching.school_year_id || teachingYearId,
      subject_id: teaching.subject_id || teachingSubjectId });
  }

  const teachingRows = Object.values((structure.subject_assignments || []).reduce((groups, item) => {
    const key = `${item.school_year_id}:${item.subject_id}:${item.teacher_user_id}`;
    if (!groups[key]) groups[key] = {
      id: key, school_year_id: item.school_year_id, subject_id: item.subject_id,
      subject_name: item.subject_name, teacher_user_id: item.teacher_user_id,
      teacher_name: item.teacher_name, section_ids: [],
      sections: [],
    };
    groups[key].section_ids.push(item.section_id);
    groups[key].sections.push(`Grade ${item.grade} · Section ${item.section_name}`);
    return groups;
  }, {}));

  const selectedTeacherId = Number(teaching.teacher_user_id);
  const selectedTeacherOtherSubjects = (structure.subject_assignments || []).filter((item) =>
    item.school_year_id === selectedYearId
      && item.teacher_user_id === selectedTeacherId
      && item.subject_id !== selectedSubjectId,
  );
  const selectedGradeCount = new Set(eligibleTeachingSections
    .filter((item) => teaching.section_ids.map(Number).includes(item.id))
    .map((item) => item.grade_level_id)).size;
  const teachingConflictMessage = selectedTeacherOtherSubjects.length
    ? `${sortedTeachers.find(item => item.id === selectedTeacherId)?.full_name || 'This teacher'} is already assigned to ${[...new Set(selectedTeacherOtherSubjects.map(item => item.subject_name))].join(', ')} this school year. Remove that assignment before assigning another subject.`
    : selectedGradeCount > 1
      ? 'Choose sections from one grade level for each teacher and subject assignment.'
      : '';

  const changeTeachingContext = (school_year_id, subject_id) => {
    setTeaching({
      id: null, school_year_id: Number(school_year_id) || '', subject_id: Number(subject_id) || '',
      teacher_user_id: '', section_ids: [],
    });
  };

  const saveTeaching = () => {
    if (teachingConflictMessage) {
      fail({ message: teachingConflictMessage });
      return;
    }
    return confirmSave('subject-teaching-assignments', teaching, () => setTeaching({
      id: null, school_year_id: teachingYearId, subject_id: teachingSubjectId, teacher_user_id: '', section_ids: [],
    }), 'Subject teaching assignment');
  };

  const removeTeaching = (item) => setConfirm({
    title: 'Remove subject teacher assignment',
    message: `Remove ${item.teacher_name} from ${item.subject_name} for ${structure.school_years.find(yearItem => yearItem.id === item.school_year_id)?.name || 'this school year'}? Existing class records and grades will be preserved.`,
    danger: true,
    onConfirm: async () => {
      setConfirm(null);
      try {
        await api.post('/admin/subject-teaching-assignments', {
          school_year_id: item.school_year_id, subject_id: item.subject_id,
          teacher_user_id: item.teacher_user_id, section_ids: [],
        });
        if (teaching.id === item.id) setTeaching({ id: null, school_year_id: item.school_year_id, subject_id: item.subject_id, teacher_user_id: '', section_ids: [] });
        success('Subject teacher assignment removed. Existing grades were preserved.');
        await reload();
      } catch (err) { fail(err); }
    },
  });

  const confirmSave = (path, value, reset, label) => {
    setConfirm({
      title: `Save ${label}`,
      message: `Are you sure you want to save changes to "${value.name || label}"? This will immediately update the academic structure.`,
      danger: false,
      onConfirm: async () => {
        setConfirm(null);
        try {
          const result = await api.post(`/admin/${path}`, value);
          reset();
          success(result.restored ? `${label} restored and updated.` : `${label} saved.`);
          await reload();
        }
        catch (err) { fail(err); }
      },
    });
  };

  const confirmDelete = (kind, item, label) => {
    const recoverable = ['school-years', 'grading-periods', 'grade-levels', 'sections', 'subjects'].includes(kind);
    setConfirm({
      title: `Delete ${label}`,
      message: recoverable
        ? `Delete "${item.name || label}" from academic setup and new class selections? Existing students, scores, attendance, and class records will be preserved. ${kind === 'grade-levels' ? 'Sections under this grade level will also be hidden until the grade level is restored. ' : kind === 'school-years' ? 'Grading periods under this school year will also be hidden until the school year is restored. ' : ''}You can restore it from Deleted items.`
        : `Are you sure you want to permanently delete "${item.name || label}"? This cannot be undone. Ensure no gradebooks or students are currently linked to it.`,
      danger: true,
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.delete(`/admin/reference/${kind}/${item.id}`);
          if (kind === 'school-years') {
            if (year.id === item.id) setYear({ id: null, name: '', starts_on: '', ends_on: '', active: true });
            if (Number(period.school_year_id) === item.id) setPeriod({ id: null, school_year_id: '', name: 'Term 1', starts_on: '', ends_on: '', active: true });
          }
          if (kind === 'grading-periods' && period.id === item.id) setPeriod({ id: null, school_year_id: firstYear, name: 'Term 1', starts_on: '', ends_on: '', active: true });
          if (kind === 'grade-levels') {
            if (grade.id === item.id) setGrade({ id: null, name: '', active: true });
            if (section.grade_level_id === item.id) setSection({ id: null, grade_level_id: '', name: '', adviser_user_id: '', adviser_name: '', track: '', track_cluster: '', active: true });
          }
          if (kind === 'sections' && section.id === item.id) setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', track: '', track_cluster: '', active: true });
          if (kind === 'subjects' && subject.id === item.id) setSubject({ id: null, code: '', name: '', category: 'JHS', is_elective: false, allowed_grades: [7, 8, 9, 10], elective_track: '', elective_cluster: '', active: true });
          success(`${label} deleted.${recoverable ? ' Linked records were preserved.' : ''}`);
          await reload();
        }
        catch (err) { fail(err); }
      },
    });
  };

  const confirmRestore = (item) => {
    setConfirm({
      title: `Restore ${item.name}`,
      message: `Restore "${item.name}" to academic setup with its previous settings?${item.kind === 'grade-levels' ? ' Its sections will be visible again unless they were deleted separately.' : item.kind === 'school-years' ? ' Its grading periods will be visible again unless they were deleted separately.' : ''}`,
      onConfirm: async () => {
        setConfirm(null);
        try { await api.post(`/admin/reference/${item.kind}/${item.id}/restore`, {}); success(`${item.name} restored.`); await reload(); }
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
      message: `Assign "${targetName}" as adviser for Section "${adviserModal.grade} - ${adviserModal.name}"? The previous adviser will lose adviser access for the selected school year; other years are unchanged.`,
      danger: false,
      onConfirm: async () => {
        setConfirm(null);
        try {
          await api.post('/admin/sections', {
            school_year_id: adviserYearId, id: adviserModal.id, grade_level_id: adviserModal.grade_level_id,
            name: adviserModal.name, adviser_user_id: newAdviserId ? Number(newAdviserId) : null,
            adviser_name: adviserModal.adviser_name, track: adviserModal.track || null,
            track_cluster: adviserModal.track_cluster || null, active: adviserModal.active,
          });
          success(`Adviser for "${adviserModal.grade} - ${adviserModal.name}" updated to ${targetName}.`);
          setAdviserModal(null); await reload();
        } catch (err) { fail(err); }
      },
    });
  };

  return (
    <div className="page-stack">
      <div className="notice notice-blue"><Database size={18} /> Set up each school year's dates and grading periods here. Grade levels, sections, and subjects are reusable definitions; adviser and subject-teacher assignments can change by year. Editing or deleting setup items preserves existing student, score, attendance, and class records. Deleted items can be restored below.</div>

      <section className="card-static">
        <details>
          <summary>Deleted items ({deletedReferences.length})</summary>
          <p className="section-copy">Restore an item to use it again. Restore a school year before its grading periods, or a grade level before its sections.</p>
          <div className="table-scroll"><table className="interactive-table">
            <thead><tr><th>Type</th><th>Name</th><th>Deleted</th><th>Action</th></tr></thead>
            <PaginatedBody>
              {deletedReferences.length === 0 && <tr><td colSpan="4" className="empty-cell">No deleted academic items.</td></tr>}
              {deletedReferences.map((item) => <tr key={`${item.kind}-${item.id}`}>
                <td>{{ 'school-years': 'School year', 'grading-periods': 'Grading period', 'grade-levels': 'Grade level', sections: 'Section', subjects: 'Subject' }[item.kind]}</td>
                <td>{item.grade ? `${item.grade} — ${item.name}` : item.name}</td>
                <td>{new Date(`${item.deleted_at}Z`).toLocaleString('en-PH')}</td>
                <td><button className="btn-secondary" disabled={!item.can_restore} onClick={() => confirmRestore(item)}>Restore</button>{!item.can_restore && <p className="section-copy">{item.restore_hint || 'Restore the parent item first.'}</p>}</td>
              </tr>)}
            </PaginatedBody>
          </table></div>
        </details>
      </section>

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
        title="Grading Periods" eyebrow="Terms and dates"
        columns={[{ key: 'school_year', label: 'School Year' }, { key: 'name', label: 'Name' }, { key: 'starts_on', label: 'Starts' }, { key: 'ends_on', label: 'Ends' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.grading_periods}
        onEdit={({ id, school_year_id, name, starts_on, ends_on, active }) => setPeriod({ id, school_year_id, name, starts_on, ends_on, active })}
        onDelete={(item) => confirmDelete('grading-periods', item, 'Grading Period')}
        form={<div className="form-grid three-columns"><label><span className="field-label">School Year</span><select className="input-field" value={period.school_year_id} onChange={(e) => setPeriod({ ...period, school_year_id: Number(e.target.value) })}>{sortedSchoolYears.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><Field label="Name (e.g. TERM 1)" value={period.name} onChange={(v) => setPeriod({ ...period, name: v })} /><Field label="Starts" type="date" value={period.starts_on} onChange={(v) => setPeriod({ ...period, starts_on: v })} /><Field label="Ends" type="date" value={period.ends_on} onChange={(v) => setPeriod({ ...period, ends_on: v })} /></div>}
        onSave={() => confirmSave('grading-periods', period, () => setPeriod({ id: null, school_year_id: firstYear, name: 'Term 1', starts_on: '', ends_on: '', active: true }), 'Grading Period')}
        onCancel={() => setPeriod({ id: null, school_year_id: firstYear, name: 'Term 1', starts_on: '', ends_on: '', active: true })}
        isEditing={Boolean(period.id)}
      />

      <AcademicCard
        title="Grade Levels" eyebrow="Year levels"
        columns={[{ key: 'name', label: 'Grade Level' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.grade_levels}
        onEdit={(item) => setGrade({ ...item })}
        onDelete={(item) => confirmDelete('grade-levels', item, 'Grade Level')}
        form={<div className="form-grid"><Field label="Grade level (e.g. 7)" value={grade.name} onChange={(v) => setGrade({ ...grade, name: v })} /></div>}
        onSave={() => confirmSave('grade-levels', grade, () => setGrade({ id: null, name: '', active: true }), 'Grade Level')}
        onCancel={() => setGrade({ id: null, name: '', active: true })}
        isEditing={Boolean(grade.id)}
      />

      <label><span className="field-label">Adviser assignment school year</span><select className="input-field" value={adviserYearId} onChange={event => { setAdviserYear(event.target.value); setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', track: '', track_cluster: '', active: true }); }}>{sortedSchoolYears.filter(year => year.active).map(year => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
      <p className="section-copy">Adviser changes apply only to this school year. Other years retain their assignments.</p>
      <AcademicCard
        title="Sections" eyebrow="Class sections and adviser assignment"
        columns={[{ key: 'grade', label: 'Grade' }, { key: 'name', label: 'Section' }, { key: 'track_label', label: 'Program / track', render: (v) => v || '—' }, { key: 'adviser_name', label: 'Adviser', render: (v) => v || <span style={{ color: 'var(--text-muted, #888)' }}>Unassigned</span> }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={yearlySections}
        onEdit={(item) => setSection({ ...item, adviser_user_id: item.adviser_user_id || '' })}
        onDelete={(item) => confirmDelete('sections', item, `Section ${item.grade} - ${item.name}`)}
        extraActions={(item) => <button onClick={() => openAdviserModal(item)}><UserCheck size={14} /> Assign adviser</button>}
        form={<div className="form-grid four-columns">
          <label><span className="field-label">Grade Level</span><select className="input-field" value={section.grade_level_id} onChange={(e) => setSection({ ...section, grade_level_id: Number(e.target.value), track: '', track_cluster: '' })}>{sortedGradeLevels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <Field label="Section name" value={section.name} onChange={(v) => setSection({ ...section, name: v })} required />
          {isJuniorHighGrade(sortedGradeLevels.find(item => item.id === Number(section.grade_level_id))?.name) ? <label><span className="field-label">JHS Program</span><select className="input-field" required value={section.track || ''} onChange={(e) => setSection({ ...section, track: e.target.value, track_cluster: '' })}><option value="">Choose program</option>{sortedJhsPrograms.map(program => <option key={program} value={program}>{program}</option>)}</select></label> : isSeniorHighGrade(sortedGradeLevels.find(item => item.id === Number(section.grade_level_id))?.name) ? <>
            <label><span className="field-label">SHS Track</span><select className="input-field" required value={section.track || ''} onChange={(e) => setSection({ ...section, track: e.target.value, track_cluster: '' })}><option value="">Choose track</option>{sortedTracks.map(track => <option key={track} value={track}>{track}</option>)}{section.track && !SHS_TRACKS.includes(section.track) && <option value={section.track}>{section.track} (legacy)</option>}</select></label>
            {SHS_TRACK_CLUSTERS[section.track] && <label><span className="field-label">SHS Cluster</span><select className="input-field" required value={section.track_cluster || ''} onChange={(e) => setSection({ ...section, track_cluster: e.target.value })}><option value="">Choose cluster</option>{SHS_TRACK_CLUSTERS[section.track].map(cluster => <option key={cluster} value={cluster}>{cluster}</option>)}</select></label>}
          </> : <span />}
        </div>}
        formNote="Each teacher can advise one section per school year and teach one subject across multiple sections in the same grade."
        onSave={() => {
          const selectedGrade = sortedGradeLevels.find(item => item.id === Number(section.grade_level_id))?.name;
          if (isJuniorHighGrade(selectedGrade) && !section.track) {
            fail({ message: 'Choose BEP or STE for this junior high section.' });
            return;
          }
          if (isSeniorHighGrade(selectedGrade) && !section.track) {
            fail({ message: 'Choose an SHS track for this section.' });
            return;
          }
          if (isSeniorHighGrade(selectedGrade) && SHS_TRACK_CLUSTERS[section.track] && !section.track_cluster) {
            fail({ message: 'Choose an elective cluster for the selected SHS track.' });
            return;
          }
          confirmSave('sections', { ...section, school_year_id: adviserYearId, adviser_user_id: section.adviser_user_id || null, track: section.track || null, track_cluster: section.track_cluster || null }, () => setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', track: '', track_cluster: '', active: true }), 'Section');
        }}
        onCancel={() => setSection({ id: null, grade_level_id: firstGrade, name: '', adviser_user_id: '', adviser_name: '', track: '', track_cluster: '', active: true })}
        isEditing={Boolean(section.id)}
      />

      <AcademicCard
        title="Subjects" eyebrow="Learning areas"
        columns={[{ key: 'name', label: 'Subject Name' }, { key: 'category', label: 'Category' }, { key: 'elective_label', label: 'Elective' }, { key: 'active', label: 'Active', render: (v) => <ActiveBadge active={v} /> }]}
        rows={structure.subjects.map(item => ({ ...item, name: String(item.category || '').toUpperCase().startsWith('SHS') ? String(item.name || '').toUpperCase() : item.name, elective_label: item.is_elective && !String(item.category).toUpperCase().startsWith('SHS') ? `STE · Grades ${(item.allowed_grades ?? [7, 8, 9, 10]).join(', ')}` : item.is_elective ? `Yes${item.elective_cluster ? ` · ${item.elective_cluster}` : item.elective_track ? ` · ${item.elective_track}` : ''}` : 'No' }))}
        onEdit={(item) => setSubject({ ...item })}
        onDelete={(item) => confirmDelete('subjects', item, 'Subject')}
        form={(
          <div className="form-grid three-columns">
            {subjectUsesJhsCatalog && !(subject.id && !selectedJhsCatalogSubject) && (
              <label>
                <span className="field-label">Approved JHS subject</span>
                <select
                  className="input-field"
                  value={selectedJhsCatalogSubject?.code || ''}
                  onChange={(event) => {
                    const selected = JHS_SUBJECT_CATALOG.find(item => item.code === event.target.value);
                    if (selected) setSubject({ ...subject, code: selected.code, name: selected.name });
                  }}
                  required
                >
                  <option value="">Choose an approved subject</option>
                  {jhsCatalogOptions.map(item => <option key={item.code} value={item.code} disabled={item.alreadyAdded}>
                    {item.name}{item.alreadyAdded ? ' (already added)' : ''}
                  </option>)}
                </select>
                <span className="muted-small">The subject code and workbook mapping are assigned automatically.</span>
              </label>
            )}
            {subjectUsesShsCoreCatalog && !(subject.id && !selectedShsCoreSubject) && (
              <label>
                <span className="field-label">Approved SHS core subject</span>
                <select
                  className="input-field"
                  value={selectedShsCoreSubject?.code || ''}
                  onChange={(event) => {
                    const selected = SHS_CORE_SUBJECT_CATALOG.find(item => item.code === event.target.value);
                    if (selected) setSubject({ ...subject, code: selected.code, name: selected.name });
                  }}
                  required
                >
                  <option value="">Choose an approved SHS core subject</option>
                  {shsCoreCatalogOptions.map(item => <option key={item.code} value={item.code} disabled={item.alreadyAdded}>
                    {item.name}{item.alreadyAdded ? ' (already added)' : ''}
                  </option>)}
                </select>
                <span className="muted-small">The code and subject name are assigned automatically from the approved SHS core list.</span>
              </label>
            )}
            {!subjectIsShsElective && (!subjectUsesJhsCatalog || Boolean(subject.id && !selectedJhsCatalogSubject))
              && (!subjectUsesShsCoreCatalog || Boolean(subject.id && !selectedShsCoreSubject)) && <>
              {!subject.is_elective && <Field label="Subject code (e.g. ENG)" value={subject.code} onChange={(v) => setSubject({ ...subject, code: v })} required />}
              <Field label="Subject name" value={subject.name} onChange={(v) => setSubject({ ...subject, name: subjectIsShs ? v.toUpperCase() : v })} required />
            </>}
            <label>
              <span className="field-label">Category</span>
              <select className="input-field" value={subjectIsShs ? 'SHS' : 'JHS'} onChange={(e) => setSubject({ ...subject, category: e.target.value, elective_track: e.target.value === 'JHS' ? '' : subject.elective_track, elective_cluster: e.target.value === 'JHS' ? '' : subject.elective_cluster })}>
                <option value="JHS">JHS (Grades 7-10)</option>
                <option value="SHS">SHS (Grades 11-12)</option>
              </select>
            </label>
            <label className="subject-elective-field">
              <span className="field-label">Subject option</span>
              <span className="subject-elective-field__control">
                <input type="checkbox" checked={Boolean(subject.is_elective)} onChange={(e) => setSubject({ ...subject, is_elective: e.target.checked, elective_track: e.target.checked ? subject.elective_track : '', elective_cluster: e.target.checked ? subject.elective_cluster : '' })} />
                <span>Elective subject</span>
              </span>
            </label>
            {!subjectIsShs && subject.is_elective && <p className="section-copy">Elective names are entered by the admin and use the approved English-derived JHS workbook template.</p>}
            {subjectIsShsElective && <label><span className="field-label">Available to SHS track</span><select className="input-field" value={subject.elective_track || ''} onChange={(e) => setSubject({ ...subject, id: null, code: '', name: '', elective_track: e.target.value, elective_cluster: '' })}><option value="">Choose track</option>{orderedElectiveTracks.map(track => <option key={track} value={track}>{track}</option>)}</select></label>}
            {subjectIsShsElective && subject.elective_track && SHS_TRACK_CLUSTERS[subject.elective_track] && <label><span className="field-label">SHS elective cluster</span><select className="input-field" required value={subject.elective_cluster || ''} onChange={(e) => setSubject({ ...subject, id: null, code: '', name: '', elective_cluster: e.target.value })}><option value="">Choose cluster</option>{SHS_TRACK_CLUSTERS[subject.elective_track].map(cluster => <option key={cluster} value={cluster}>{cluster}</option>)}</select></label>}
            {subjectIsShsElective && subject.elective_cluster && <label><span className="field-label">Subject name</span><select className="input-field" required disabled={!shsElectiveOptions.length} value={selectedShsElectiveSubject?.name || ''} onChange={(e) => {
              const name = normalizeSubjectName(e.target.value);
              const existing = shsElectiveOptions.find(item => item.name === name)?.existing;
              setSubject({ ...subject, id: existing?.id || null, code: existing?.code || '', name, active: existing?.active ?? true });
            }}><option value="">{shsElectiveOptions.length ? 'Choose an approved elective subject' : 'No approved subjects listed for this cluster yet'}</option>{shsElectiveOptions.map(item => <option key={item.name} value={item.name}>{item.name}{item.alreadyAdded ? ' (existing subject — will be updated)' : ''}</option>)}</select><span className="muted-small">Choose from the approved cluster list. Existing SHS subjects with the same name will be updated instead of duplicated.</span></label>}
            {!subjectIsShs && subject.is_elective && <fieldset className="elective-grade-picker" aria-describedby="elective-grade-help"><legend>Allowed JHS grades</legend><div className="elective-grade-picker__intro"><p id="elective-grade-help">Choose the grade levels that can take this elective. Applies to STE sections.</p><span className="elective-grade-picker__count">{(subject.allowed_grades ?? [7, 8, 9, 10]).length} selected</span></div><div className="elective-grade-picker__options">{[7, 8, 9, 10].map(grade => <label key={grade} className="elective-grade-picker__option"><input type="checkbox" checked={(subject.allowed_grades ?? [7, 8, 9, 10]).includes(grade)} onChange={event => setSubject({ ...subject, allowed_grades: event.target.checked ? [...(subject.allowed_grades ?? [7, 8, 9, 10]), grade] : (subject.allowed_grades ?? [7, 8, 9, 10]).filter(value => value !== grade) })} /><span>Grade {grade}</span></label>)}</div><p className="elective-grade-picker__hint">Select one or more grades. Existing class records are preserved.</p>{!(subject.allowed_grades ?? [7, 8, 9, 10]).length && <p className="elective-grade-picker__error" role="status">Choose at least one grade before saving.</p>}</fieldset>}
          </div>
        )}
        onSave={() => {
          if (subjectUsesJhsCatalog && !subject.id && !selectedJhsCatalogSubject) return showError('Choose one of the approved JHS subjects.');
          if (subjectUsesShsCoreCatalog && !subject.id && !selectedShsCoreSubject) return showError('Choose one of the approved SHS core subjects.');
          if (subject.is_elective && !subjectIsShs && !(subject.allowed_grades ?? [7, 8, 9, 10]).length) return showError('Select at least one allowed JHS grade.');
          if (subjectIsShs && subject.is_elective && !subject.elective_track) return showError('Choose the SHS track for this elective.');
          if (subjectIsShs && subject.is_elective && SHS_TRACK_CLUSTERS[subject.elective_track] && !subject.elective_cluster) return showError('Choose the SHS cluster for this elective.');
          if (subjectIsShsElective && !selectedShsElectiveSubject) return showError('Choose an SHS elective from the approved subject list for this cluster.');
          const saveValue = subjectIsShs ? {
            ...subject,
            code: subject.code || (subjectUsesShsCoreCatalog ? selectedShsCoreSubject?.code : ''),
            name: normalizeSubjectName(selectedShsCoreSubject?.name || subject.name),
          } : subject;
          confirmSave('subjects', saveValue, () => setSubject({ id: null, code: '', name: '', category: 'JHS', is_elective: false, allowed_grades: [7, 8, 9, 10], elective_track: '', elective_cluster: '', active: true }), 'Subject');
        }}
        onCancel={() => setSubject({ id: null, code: '', name: '', category: 'JHS', is_elective: false, allowed_grades: [7, 8, 9, 10], elective_track: '', elective_cluster: '', active: true })}
        isEditing={Boolean(subject.id)}
      />

      <AcademicCard
        title="Subject Teaching Assignments" eyebrow="Teacher and class responsibility"
        columns={[{ key: 'school_year_name', label: 'School Year' }, { key: 'subject_name', label: 'Subject' }, { key: 'teacher_name', label: 'Teacher' }, { key: 'sections_label', label: 'Assigned Grade / Section(s)' }]}
        rows={teachingRows.map(item => ({ ...item,
          school_year_name: structure.school_years.find(yearItem => yearItem.id === item.school_year_id)?.name || '—',
          sections_label: item.sections.join(', '),
        }))}
        onEdit={(item) => setTeaching({ ...item })}
        onDelete={removeTeaching}
        form={<div className="form-grid two-columns"><label><span className="field-label">School year</span><select className="input-field" value={teaching.school_year_id || teachingYearId} onChange={(e) => changeTeachingContext(e.target.value, teaching.subject_id || teachingSubjectId)}>{orderedOptions(structure.school_years.filter(item => item.active)).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span className="field-label">Subject</span><select className="input-field" value={teaching.subject_id || teachingSubjectId} onChange={(e) => changeTeachingContext(teaching.school_year_id || teachingYearId, e.target.value)}>{orderedOptions(structure.subjects.filter(item => item.active), (item) => `${item.name} (${item.category})`).map(item => <option key={item.id} value={item.id}>{item.name} ({item.category})</option>)}</select></label><label><span className="field-label">Subject teacher</span><select className="input-field" value={teaching.teacher_user_id || ''} onChange={(e) => setTeaching({ ...teaching, teacher_user_id: e.target.value ? Number(e.target.value) : '' })}><option value="">Choose teacher</option>{sortedTeachers.map(item => <option key={item.id} value={item.id}>{item.full_name} ({item.username})</option>)}</select></label><SectionAssignmentPicker sections={eligibleTeachingSections} selectedIds={teaching.section_ids} onChange={(section_ids) => setTeaching({ ...teaching, section_ids })} /></div>}
        formNote="Assign a teacher to one subject per school year. A teacher may cover multiple sections in one grade; different grades or sections may have different teachers for the same subject. Reassigning a section leaves other teachers’ assignments unchanged."
        onSave={saveTeaching}
        onCancel={() => setTeaching({ id: null, school_year_id: teachingYearId, subject_id: teachingSubjectId, teacher_user_id: '', section_ids: [] })}
        isEditing={Boolean(teaching.id)}
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
                {sortedTeachers.map((t) => <option key={t.id} value={t.id}>{t.full_name} ({t.username})</option>)}
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
