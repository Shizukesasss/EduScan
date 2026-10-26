import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, FileCheck2, FileClock, FileText, UserPlus } from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import './AnnexGWorkspace.css';

export default function AnnexGWorkspace() {
  const { showError, showSuccess } = useToast();
  const role = auth.role();
  const [options, setOptions] = useState({ school_years: [], can_manage_placements: false, can_release: false });
  const [schoolYearId, setSchoolYearId] = useState('');
  const [grade, setGrade] = useState('');
  const [section, setSection] = useState('');
  const [term, setTerm] = useState('1');
  const [report, setReport] = useState(null);
  const [failedQuery, setFailedQuery] = useState('');
  const [comments, setComments] = useState({});
  const [placementCandidates, setPlacementCandidates] = useState([]);
  const [placementLoading, setPlacementLoading] = useState(false);
  const [placementError, setPlacementError] = useState('');
  const [reviewingPersonId, setReviewingPersonId] = useState(null);
  const [savingPlacementId, setSavingPlacementId] = useState(null);
  const [placementForm, setPlacementForm] = useState({ grade_level_id: '', section_id: '', starts_on: '', confirmed: false });
  const years = options.school_years || [];
  const selectedYear = years.find((year) => String(year.id) === String(schoolYearId));
  const placementGrades = [...new Set((selectedYear?.sections || []).map((item) => item.grade))].sort((a, b) => Number(a) - Number(b));
  const selectedPlacementGradeId = Number(placementForm.grade_level_id);
  const placementSections = (selectedYear?.sections || []).filter((item) => item.grade_level_id === selectedPlacementGradeId);
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
    if (!options.can_manage_placements || !schoolYearId) return undefined;
    let cancelled = false;
    api.get(`/admin/annex-g/placement-candidates?school_year_id=${schoolYearId}`)
      .then((result) => { if (!cancelled) setPlacementCandidates(result.candidates || []); })
      .catch((error) => { if (!cancelled) { setPlacementError(error.message); showError(error.message); } })
      .finally(() => { if (!cancelled) setPlacementLoading(false); });
    return () => { cancelled = true; };
  }, [options.can_manage_placements, schoolYearId, showError]);

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

  const savePlacement = async (candidate) => {
    setSavingPlacementId(candidate.id);
    try {
      await api.post('/admin/annex-g/placements', {
        person_id: candidate.id, school_year_id: Number(schoolYearId),
        grade_level_id: Number(placementForm.grade_level_id), section_id: Number(placementForm.section_id),
        starts_on: placementForm.starts_on,
        confirmed: placementForm.confirmed,
      });
      showSuccess(`Grade ${selectedYear?.sections.find((item) => item.grade_level_id === Number(placementForm.grade_level_id))?.grade} · ${placementSections.find((item) => item.id === Number(placementForm.section_id))?.section} placement saved for ${candidate.full_name}.`);
      setReviewingPersonId(null);
      setPlacementForm({ grade_level_id: '', section_id: '', starts_on: '', confirmed: false });
      const refreshed = await api.get(`/admin/annex-g/placement-candidates?school_year_id=${schoolYearId}`);
      setPlacementCandidates(refreshed.candidates || []);
    } catch (error) { showError(error.message); }
    finally { setSavingPlacementId(null); }
  };

  return <section className="card-static annex-g-workspace">
    <div className="section-heading"><div><p className="eyebrow">Grades 7–10 · adviser draft / records release</p><h2>Annex G learner reports</h2></div><FileText size={24} /></div>
    <p className="section-copy">Uses verified school-year enrollment, calculated age, finalized grades, and recorded attendance. Missing source data blocks release; this workspace never edits scores or attendance.</p>
    <div className="form-grid three-columns">
      <label><span className="field-label">School year</span><select className="input-field" value={schoolYearId} onChange={(event) => { setSchoolYearId(event.target.value); setReviewingPersonId(null); setPlacementCandidates([]); setPlacementLoading(Boolean(event.target.value)); setPlacementError(''); setPlacementForm({ grade_level_id: '', section_id: '', starts_on: '', source_reference: '', confirmed: false }); }}><option value="">Choose school year</option>{years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
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
    {options.can_manage_placements && <details className="annex-g-placement-review">
      <summary><UserPlus size={16} /> Review existing learner placements</summary>
      <p className="section-copy">For SY {selectedYear?.name || '—'}, choose each learner’s grade, section, and start date from a verified school record. Current profile details are shown only for context and are not treated as history. Missing dates of birth can be entered in Administration → People & Records.</p>
      {placementLoading && <p className="muted-small">Loading learners without a placement…</p>}
      {placementError && <p className="notice notice-danger" role="alert">Learners could not be loaded: {placementError}</p>}
      {!placementLoading && !placementError && placementCandidates.length === 0 && <p className="empty-cell">All active learners already have a placement for this school year, or no student records are available.</p>}
      {placementCandidates.map((candidate) => <article className="annex-g-placement-candidate" key={candidate.id}>
        <div className="annex-g-placement-heading"><div><strong>{candidate.full_name}</strong><span>{candidate.lrn || 'LRN not recorded'} · Current profile: {candidate.current_grade ? `Grade ${candidate.current_grade} · ${candidate.current_section || 'Section not set'}` : 'grade/section not set'} (context only)</span></div>
          {reviewingPersonId !== candidate.id && <button type="button" className="btn-secondary" onClick={() => { setReviewingPersonId(candidate.id); setPlacementForm({ grade_level_id: '', section_id: '', starts_on: '', confirmed: false }); }}>Review placement</button>}
        </div>
        {reviewingPersonId === candidate.id && <div className="annex-g-placement-form">
          <div className="form-grid three-columns">
            <label><span className="field-label">Verified grade</span><select className="input-field" value={placementGrades.find((grade) => selectedYear?.sections.find((item) => item.grade === grade)?.grade_level_id === selectedPlacementGradeId) || ''} onChange={(event) => { const target = selectedYear?.sections.find((item) => item.grade === event.target.value); setPlacementForm((current) => ({ ...current, grade_level_id: String(target?.grade_level_id || ''), section_id: '' })); }} required><option value="">Choose grade</option>{placementGrades.map((item) => <option key={item} value={item}>Grade {item}</option>)}</select></label>
            <label><span className="field-label">Verified section</span><select className="input-field" value={placementForm.section_id} onChange={(event) => setPlacementForm((current) => ({ ...current, section_id: event.target.value }))} disabled={!placementForm.grade_level_id} required><option value="">Choose section</option>{placementSections.map((item) => <option key={item.id} value={item.id}>{item.section}</option>)}</select></label>
            <label><span className="field-label">Enrollment start date</span><input className="input-field" type="date" min={selectedYear?.starts_on || undefined} max={selectedYear?.ends_on || undefined} value={placementForm.starts_on} onChange={(event) => setPlacementForm((current) => ({ ...current, starts_on: event.target.value }))} required /></label>
          </div>
          <label className="checkbox-field"><input type="checkbox" checked={placementForm.confirmed} onChange={(event) => setPlacementForm((current) => ({ ...current, confirmed: event.target.checked }))} required /><span>I verified this learner’s placement and start date against an official school record.</span></label>
          <div className="action-row"><button type="button" className="btn-secondary" onClick={() => setReviewingPersonId(null)} disabled={savingPlacementId === candidate.id}>Cancel</button><button type="button" className="btn-primary" onClick={() => savePlacement(candidate)} disabled={savingPlacementId === candidate.id || !placementForm.grade_level_id || !placementForm.section_id || !placementForm.starts_on || !placementForm.confirmed}>{savingPlacementId === candidate.id ? 'Saving placement…' : 'Save verified placement'}</button></div>
        </div>}
      </article>)}
    </details>}
  </section>;
}

function FragmentRows({ area }) {
  return <>
    <tr><th>{area.name}</th>{[1, 2, 3].map((number) => <td key={number}>{area.term_grades?.[number] ?? '—'}</td>)}<td>{area.final_grade ?? '—'}</td><td>{area.remarks || '—'}</td></tr>
    {area.subareas?.map((subarea) => <tr className="table-subrow" key={subarea.name}><td>↳ {subarea.name}</td>{[1, 2, 3].map((number) => <td key={number}>{subarea.term_grades?.[number] ?? '—'}</td>)}<td>{subarea.final_grade ?? '—'}</td><td>{subarea.descriptor || '—'}</td></tr>)}
  </>;
}
