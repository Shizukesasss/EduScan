import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, FileCheck2, FileClock, FileText, Upload } from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import './AnnexGWorkspace.css';

export default function AnnexGWorkspace() {
  const { showError, showSuccess } = useToast();
  const role = auth.role();
  const [options, setOptions] = useState({ school_years: [], can_import: false, can_release: false });
  const [schoolYearId, setSchoolYearId] = useState('');
  const [grade, setGrade] = useState('');
  const [section, setSection] = useState('');
  const [term, setTerm] = useState('1');
  const [report, setReport] = useState(null);
  const [failedQuery, setFailedQuery] = useState('');
  const [comments, setComments] = useState({});
  const [imports, setImports] = useState({ enrollment: { file: null, reference: '', result: null }, dob: { file: null, reference: '', result: null } });
  const [importBusy, setImportBusy] = useState('');
  const years = options.school_years || [];
  const selectedYear = years.find((year) => String(year.id) === String(schoolYearId));
  const grades = useMemo(() => [...new Set((selectedYear?.sections || []).map((item) => item.grade))].sort((a, b) => Number(a) - Number(b)), [selectedYear]);
  const selectedGrade = grades.includes(grade) ? grade : (grades[0] || '');
  const sections = (selectedYear?.sections || []).filter((item) => item.grade === selectedGrade);
  const selectedSection = sections.some((item) => item.section === section) ? section : (sections[0]?.section || '');
  const selectedTerm = selectedYear?.terms.includes(Number(term)) ? Number(term) : (selectedYear?.terms[0] || 1);
  const selectionQuery = schoolYearId && selectedGrade && selectedSection
    ? new URLSearchParams({ school_year_id: schoolYearId, grade: selectedGrade, section: selectedSection, term_order: String(selectedTerm) }).toString()
    : '';
  const reportMatches = report && report.school_year_id === Number(schoolYearId) && report.grade === selectedGrade
    && report.section === selectedSection && report.term_order === selectedTerm;
  const loading = Boolean(selectionQuery && !reportMatches && failedQuery !== selectionQuery);

  const loadOptions = useCallback(async () => {
    try {
      const result = await api.get('/annex-g/options');
      setOptions(result);
      setSchoolYearId((current) => result.school_years.some((item) => String(item.id) === String(current))
        ? current : String(result.school_years[0]?.id || ''));
    } catch (error) { showError(error.message); }
  }, [showError]);
  useEffect(() => {
    let cancelled = false;
    api.get('/annex-g/options').then((result) => {
      if (cancelled) return;
      setOptions(result);
      setSchoolYearId((current) => result.school_years.some((item) => String(item.id) === String(current))
        ? current : String(result.school_years[0]?.id || ''));
    }).catch((error) => { if (!cancelled) showError(error.message); });
    return () => { cancelled = true; };
  }, [showError]);

  useEffect(() => {
    if (!selectionQuery) return undefined;
    let cancelled = false;
    api.get(`/annex-g/section?${selectionQuery}`).then((result) => {
      if (cancelled) return;
      setReport(result);
      setFailedQuery('');
      setComments(Object.fromEntries(result.learners.map((learner) => [learner.enrollment_id, learner.comments?.[String(selectedTerm)] || ''])));
    }).catch((error) => { if (!cancelled) { setFailedQuery(selectionQuery); showError(error.message); } });
    return () => { cancelled = true; };
  }, [selectionQuery, selectedTerm, showError]);

  const saveComment = async (learner) => {
    try {
      await api.put('/annex-g/comments', { enrollment_id: learner.enrollment_id, term_order: selectedTerm, comment: comments[learner.enrollment_id] || '' });
      showSuccess(`Term ${selectedTerm} comment saved for ${learner.full_name}.`);
      const query = new URLSearchParams({ school_year_id: schoolYearId, grade: selectedGrade, section: selectedSection, term_order: selectedTerm });
      setReport(await api.get(`/annex-g/section?${query}`));
    } catch (error) { showError(error.message); }
  };

  const preview = (learner) => api.printHtml(`/annex-g/preview/${learner.enrollment_id}?term_order=${selectedTerm}`).catch((error) => showError(error.message));
  const release = async (learner) => {
    try {
      const item = await api.post(`/annex-g/release/${learner.enrollment_id}?term_order=${selectedTerm}`, {});
      showSuccess(`Annex G released for ${learner.full_name}, Term ${selectedTerm}.`);
      await loadOptions();
      const query = new URLSearchParams({ school_year_id: schoolYearId, grade: selectedGrade, section: selectedSection, term_order: selectedTerm });
      setReport(await api.get(`/annex-g/section?${query}`));
      await api.printHtml(`/annex-g/releases/${item.id}`);
    } catch (error) {
      const blockers = error.details?.blockers;
      showError(blockers?.length ? `${error.message} ${blockers.join(' ')}` : error.message);
    }
  };

  const updateImport = (kind, changes) => setImports((current) => ({ ...current, [kind]: { ...current[kind], ...changes, result: null } }));
  const importWorkbook = async (kind, dryRun) => {
    const item = imports[kind];
    if (!item.file || !item.reference.trim()) { showError('Choose an approved workbook and enter its school document reference.'); return; }
    const body = new FormData();
    body.append('file', item.file);
    body.append('approved_reference', item.reference.trim());
    body.append('dry_run', String(dryRun));
    setImportBusy(`${kind}-${dryRun ? 'preview' : 'apply'}`);
    try {
      const result = await api.post(`/admin/annex-g/${kind === 'enrollment' ? 'enrollments' : 'dobs'}/import`, body);
      updateImport(kind, { result });
      if (!dryRun) { showSuccess(`${kind === 'enrollment' ? 'Enrollment' : 'DOB'} import applied.`); await loadOptions(); }
    } catch (error) { showError(error.message); }
    finally { setImportBusy(''); }
  };

  return <section className="card-static annex-g-workspace">
    <div className="section-heading"><div><p className="eyebrow">Grades 7–10 · adviser draft / records release</p><h2>Annex G learner reports</h2></div><FileText size={24} /></div>
    <p className="section-copy">Uses verified school-year enrollment, calculated age, finalized grades, and recorded attendance. Missing source data blocks release; this workspace never edits scores or attendance.</p>
    <div className="form-grid three-columns">
      <label><span className="field-label">School year</span><select className="input-field" value={schoolYearId} onChange={(event) => setSchoolYearId(event.target.value)}><option value="">Choose school year</option>{years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
      <label><span className="field-label">Grade</span><select className="input-field" value={selectedGrade} onChange={(event) => setGrade(event.target.value)}><option value="">Choose grade</option>{grades.map((item) => <option key={item} value={item}>Grade {item}</option>)}</select></label>
      <label><span className="field-label">Section</span><select className="input-field" value={selectedSection} onChange={(event) => setSection(event.target.value)}><option value="">Choose section</option>{sections.map((item) => <option key={item.id} value={item.section}>{item.section}</option>)}</select></label>
      <label><span className="field-label">Report term</span><select className="input-field" value={selectedTerm} onChange={(event) => setTerm(event.target.value)}>{(selectedYear?.terms || []).map((item) => <option key={item} value={item}>Term {item}</option>)}</select></label>
    </div>
    {reportMatches && <div className="annex-g-context"><strong>Grade {report.grade} · {report.section}</strong><span>SY {report.school_year} · Term {report.term_order}: {report.term_name}</span><span>Adviser: {report.adviser_name || 'Not assigned'}</span><span>Age reference: {report.age_reference_date}</span></div>}
    {loading && <p className="muted-small">Loading verified enrollment and term records…</p>}
    {!selectionQuery && <p className="empty-cell">No Grade 7–10 section is available for this account.</p>}
    {!loading && failedQuery === selectionQuery && selectionQuery && <p className="empty-cell">The report could not be loaded for this selection.</p>}
    {reportMatches && report.blockers?.length > 0 && <div className="annex-g-blockers"><strong>Section setup needs attention</strong><ul>{report.blockers.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    {reportMatches && <div className="annex-g-learners">{report.learners.map((learner) => <article className="annex-g-learner" key={learner.enrollment_id}>
      <div className="annex-g-learner-heading"><div><h3>{learner.full_name}</h3><p>{learner.lrn || 'LRN not recorded'} · Age {learner.age ?? 'missing'}</p></div><span className={learner.blockers.length ? 'tag tag-warning' : 'tag tag-success'}>{learner.blockers.length ? `${learner.blockers.length} item(s) to resolve` : 'Ready for review'}</span></div>
      {learner.blockers.length > 0 && <div className="annex-g-blockers"><strong>Needs attention</strong><ul>{learner.blockers.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      <div className="table-scroll"><table className="interactive-table"><thead><tr><th>Learning area</th><th>Term 1</th><th>Term 2</th><th>Term 3</th><th>Final grade</th><th>Remarks</th></tr></thead><tbody>{learner.learning_areas.map((area) => <FragmentRows key={area.name} area={area} />)}</tbody></table></div>
      {role === 'teacher' && <label><span className="field-label">Term {selectedTerm} teacher comment / recommendation</span><textarea className="input-field" rows="3" maxLength="2000" value={comments[learner.enrollment_id] || ''} onChange={(event) => setComments((current) => ({ ...current, [learner.enrollment_id]: event.target.value }))} /></label>}
      <div className="action-row"><button className="btn-secondary" onClick={() => preview(learner)}><FileText size={16} /> Preview draft</button>{role === 'teacher' && <button className="btn-primary" onClick={() => saveComment(learner)}>Save term comment</button>}{options.can_release && <button className="btn-primary" disabled={learner.blockers.length > 0 || report.blockers.length > 0} onClick={() => release(learner)}><FileCheck2 size={16} /> Release this learner’s report</button>}</div>
      {report.released_reports?.filter((item) => item.parameters.enrollment_id === learner.enrollment_id).map((item) => <div className="annex-g-release-history" key={item.id}><FileClock size={16} /><span>{item.status} · {new Date(item.created_at).toLocaleString('en-PH')} · {item.generated_by_name}</span><button className="btn-link" onClick={() => api.printHtml(`/annex-g/releases/${item.id}`).catch((error) => showError(error.message))}><Download size={14} /> Open snapshot</button></div>)}
    </article>)}</div>}
    {options.can_import && <details className="annex-g-import"><summary><Upload size={16} /> Verified source records (Administrator)</summary><p className="section-copy">Imports match existing learners by exact LRN. Enrollment data does not change current placement; DOB imports fill blanks only.</p>{['enrollment', 'dob'].map((kind) => <div className="annex-g-import-row" key={kind}><div><strong>{kind === 'enrollment' ? 'School-year enrollment roster' : 'Learner date-of-birth source'}</strong><p className="muted-small">{kind === 'enrollment' ? 'Required columns: LRN, School Year, Grade, Section, Enrollment Start. Enrollment End is optional.' : 'Required columns: LRN, Date of Birth.'}</p></div><input type="file" accept=".xlsx" onChange={(event) => updateImport(kind, { file: event.target.files?.[0] || null })} /><input className="input-field" placeholder="Approved school record reference" value={imports[kind].reference} onChange={(event) => updateImport(kind, { reference: event.target.value })} /><button className="btn-secondary" disabled={importBusy !== ''} onClick={() => importWorkbook(kind, true)}>Preview</button><button className="btn-primary" disabled={importBusy !== '' || !imports[kind].result || imports[kind].result.invalid_rows > 0 || imports[kind].result.valid_rows < 1} onClick={() => importWorkbook(kind, false)}>Apply</button>{imports[kind].result && <p className="muted-small">{imports[kind].result.valid_rows} valid · {imports[kind].result.invalid_rows} invalid · {imports[kind].result.would_skip_existing ?? 0} existing DOBs skipped{imports[kind].result.errors?.map((error) => <span className="table-subline" key={error.row}>Row {error.row}: {error.errors.join(' ')}</span>)}</p>}</div>)}</details>}
  </section>;
}

function FragmentRows({ area }) {
  return <>
    <tr><th>{area.name}</th>{[1, 2, 3].map((number) => <td key={number}>{area.term_grades?.[number] ?? '—'}</td>)}<td>{area.final_grade ?? '—'}</td><td>{area.remarks || '—'}</td></tr>
    {area.subareas?.map((subarea) => <tr className="table-subrow" key={subarea.name}><td>↳ {subarea.name}</td>{[1, 2, 3].map((number) => <td key={number}>{subarea.term_grades?.[number] ?? '—'}</td>)}<td>{subarea.final_grade ?? '—'}</td><td>{subarea.descriptor || '—'}</td></tr>)}
  </>;
}
