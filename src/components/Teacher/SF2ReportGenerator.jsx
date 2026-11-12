import PaginatedBody from '../Common/PaginatedBody';
import { useCallback, useEffect, useState } from 'react';
import { api, auth, displayTime, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function SF2ReportGenerator() { return auth.role() === 'admin' ? <AdminSF2ReportGenerator /> : null; }

function AdminSF2ReportGenerator() {
  const [month, setMonth] = useState(localDate().slice(0, 7));
  const [grade, setGrade] = useState('');
  const [section, setSection] = useState('');
  const [availableSections, setAvailableSections] = useState([]);
  const schoolId = '301874';
  const [schoolYears, setSchoolYears] = useState([]);
  const [attendanceDate, setAttendanceDate] = useState('');
  const [previewDate, setPreviewDate] = useState('');
  const [previewContext, setPreviewContext] = useState('');
  const [unresolved, setUnresolved] = useState(0);
  const context = `${month}|${grade}|${section}|${attendanceDate}`;
  const loading = previewContext !== context;
  const [year, monthNumber] = month.split('-').map(Number);
  const lastDay = String(new Date(year, monthNumber, 0).getDate()).padStart(2, '0');
  const [schoolYear, setSchoolYear] = useState('');
  const [todayRows, setTodayRows] = useState([]);
  const [template, setTemplate] = useState({ configured: false });
  const { showSuccess, showError } = useToast();

  useEffect(() => {
    Promise.all([api.get('/sf2/template'), api.get('/admin/academic-structure')]).then(([status, academic]) => {
      const sections = academic.sections.filter((item) => item.active).map((item) => ({ ...item, section: item.name }));
      const years = [...academic.school_years].sort((a,b) => a.name.localeCompare(b.name)); setSchoolYears(years); setSchoolYear(years.find(item => item.starts_on.slice(0,7) <= localDate().slice(0,7) && item.ends_on.slice(0,7) >= localDate().slice(0,7))?.name || '');
      setAvailableSections(sections); setTemplate(status);
      if (sections.length) { setGrade(sections[0].grade); setSection(sections[0].section); }
    }).catch((err) => showError(err.message));
  }, [showError]);

  const load = useCallback(() => {
    if (!grade || !section) return;
    if (!month) return;
    const query = new URLSearchParams({ year, month: monthNumber, grade, section });
    if (attendanceDate) query.set('attendance_date', attendanceDate);
    let cancelled = false;
    api.get(`/sf2/preview?${query}`).then(result => { if (!cancelled) { setTodayRows(result.rows); setPreviewDate(result.preview_date); setUnresolved(result.unresolved_count); setPreviewContext(context); } })
      .catch(err => { if (!cancelled) { setTodayRows([]); showError(err.message); } });
    return () => { cancelled = true; };
  }, [attendanceDate, context, grade, month, monthNumber, section, showError, year]);
  useEffect(load, [load]);

  const students = todayRows;
  const male = students.filter((student) => student.sex === 'Male').length;
  const female = students.filter((student) => student.sex === 'Female').length;
  const overflow = male > 21 || female > 25;
  const placement = new Map();
  for (const [sex, firstRow] of [['Male', 14], ['Female', 36]]) students.filter(item => item.sex === sex).sort((a,b) => a.full_name.localeCompare(b.full_name)).forEach((item,index) => placement.set(item.person_id, firstRow + index));
  const sectionKey = `${grade}|${section}`;

  const chooseSection = (value) => {
    const item = availableSections.find((row) => `${row.grade}|${row.section}` === value);
    if (item) { setGrade(item.grade); setSection(item.section); }
  };
  const upload = async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    const form = new FormData(); form.append('file', file);
    try { await api.post('/sf2/template', form); setTemplate({ configured: true, filename: file.name }); showSuccess('Official SF2 template uploaded and validated.'); }
    catch (err) { showError(err.message); }
  };
  const downloadTemporaryLog = (format) => {
    const date = previewDate;
    const query = new URLSearchParams({ date, grade, section, format });
    api.download(`/attendance/temporary-log?${query}`, `attendance-${date}-Grade-${grade}-${section}.${format}`).catch((err) => showError(err.message));
  };
  const exportFile = async (format) => {
    const query = new URLSearchParams({ year, month: monthNumber, grade, section, school_id: schoolId, school_year: schoolYear, school_name: 'SAN JOSE NATIONAL HIGH SCHOOL', format });
    try {
      await api.download(`/sf2/export?${query}`, `SF2-${month}-${grade}-${section}.${format}`);
      showSuccess('SF2 report generated. The records officer must verify it before submission.');
    }
    catch (err) { showError(err.message); }
  };
  const exportDisabled = loading || unresolved > 0 || overflow || !template.configured || !month || !grade || !section || !schoolYear;

  return <div className="page-stack">
    <section className="card-static">
      <div className="section-heading"><div><p className="eyebrow">Official report generation</p><h2>SF2 monthly attendance report</h2><p className="section-copy">Select an active section. An assigned adviser is optional. Learners are deduplicated by ID/LRN, alphabetized within the male/female blocks, and transfer/departure remarks are written into the official remarks field.</p></div></div>
      {availableSections.length === 0 && <div className="notice notice-warning">No active section is available. Create a grade and section in Administration before generating an SF2.</div>}
      <div className="form-grid three-columns">
        <label><span className="field-label">Reporting month</span><input title="Choose the reporting month and year" className="input-field" type="month" value={month} onChange={event => { const value = event.target.value; setMonth(value); setAttendanceDate(''); const selected = schoolYears.find(item => item.starts_on.slice(0,7) <= value && item.ends_on.slice(0,7) >= value); setSchoolYear(selected?.name || ''); }} /></label>
        <label><span className="field-label">Section</span><select className="input-field" value={sectionKey} onChange={(event) => chooseSection(event.target.value)}>{availableSections.map((item) => <option key={item.id} value={`${item.grade}|${item.section}`}>Grade {item.grade} — {item.section}{item.adviser_name ? ` · ${item.adviser_name}` : ' · No adviser assigned'}</option>)}</select></label>
        <label><span className="field-label">School year</span><select className="input-field" value={schoolYear} onChange={event => setSchoolYear(event.target.value)}><option value="">Choose a school year</option>{schoolYears.map(item => <option key={item.id}>{item.name}</option>)}</select></label>
        <label><span className="field-label">School ID</span><input placeholder="Enter school id" className="input-field" value={schoolId} readOnly /></label>
      </div>
      <div className="report-action-bar">
        <div><strong>{loading ? 'Loading monthly roster...' : `${students.length} learner(s)`}</strong><span>{male} male · {female} female · {template.configured ? template.filename : 'Template missing'}</span></div>
        <div className="action-row">
          <details className="action-menu">
            <summary>Supporting files</summary>
            <div className="action-menu-panel">
              {auth.role() === 'admin' && <label> {template.configured ? 'Replace official template' : 'Upload official template'}<input title="Choose a file in the format shown by this field" type="file" accept=".xlsx" onChange={upload} hidden /></label>}
              <button disabled={loading || !previewDate} onClick={() => downloadTemporaryLog('pdf')}>Download section log PDF</button>
              <button disabled={loading || !previewDate} onClick={() => downloadTemporaryLog('xlsx')}>Download section log Excel (.xlsx)</button>
            </div>
          </details>
          <button className="btn-primary" disabled={exportDisabled} onClick={() => exportFile('pdf')}>Download SF2 PDF</button>
          <button className="btn-secondary" disabled={exportDisabled} onClick={() => exportFile('xlsx')}>Download SF2 Excel (.xlsx)</button>
        </div>
      </div>
      {!loading && unresolved > 0 && <div className="notice notice-warning" role="status">{unresolved} learner-day(s) still have No scan on past school days. Review or close those days in Attendance before generating official SF2. This screen does not create absences.</div>}
      {overflow && <div className="notice notice-danger"> Template capacity exceeded: {male}/21 male and {female}/25 female learners. Resolve the roster before export.</div>}
    </section>
    <section className="card-static">
      <div className="section-heading">
        <div><h2>Selected-month roster preview</h2><p className="section-copy">The official export contains the full month. “No scan” remains pending until authorized daily close or correction.</p></div>
        {month && <label>
          <span className="field-label">Attendance date</span>
          <input className="input-field" type="date" min={`${month}-01`} max={`${month}-${lastDay}`}
            value={attendanceDate || (!loading ? previewDate : '')} onChange={(event) => {
              if (event.target.validity.valid) setAttendanceDate(event.target.value);
            }} />
        </label>}
      </div>
      <div className="table-scroll">
        <table className="interactive-table" aria-label="SF2 daily attendance preview">
          <thead><tr>
            <th>SF2 row</th><th>Learner</th><th>ID / LRN</th><th>Sex block</th><th>Movement</th>
            <th>AM Time In</th><th>AM Time Out</th><th>AM Status</th>
            <th>PM Time In</th><th>PM Time Out</th><th>PM Status</th>
            <th>Status</th><th>Template mark</th>
          </tr></thead>
          <PaginatedBody pageSize={5} resetKey={context}>
            {(!loading ? students : []).map((student) => {
              const mark = student.status === 'Absent' ? 'X' : student.status === 'Late' ? 'Upper-half shade'
                : ['Present', 'Time Out'].includes(student.status) ? 'Blank (present)' : student.status;
              return <tr key={student.person_id}>
                <td><strong>{placement.get(student.person_id)}</strong></td><td>{student.full_name}</td>
                <td>{student.external_id}{student.lrn ? ` / ${student.lrn}` : ''}</td><td>{student.sex}</td>
                <td>{student.enrollment_status}{student.transfer_school && <span className="table-subline">{student.transfer_school}</span>}</td>
                <td>{displayTime(student.am_arrival)}</td><td>{displayTime(student.am_departure)}</td><td>{student.am_status}</td>
                <td>{displayTime(student.pm_arrival)}</td><td>{displayTime(student.pm_departure)}</td><td>{student.pm_status}</td>
                <td>{student.status}</td><td>{mark}</td>
              </tr>;
            })}
          </PaginatedBody>
        </table>
      </div>
    </section>
  </div>;
}
