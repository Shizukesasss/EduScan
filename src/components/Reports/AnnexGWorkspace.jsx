import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { annexGReportSections, preferredAnnexGYear } from '../../services/annexGSelection';
import './AnnexGWorkspace.css';

export default function AnnexGWorkspace() {
  const { showError, showSuccess } = useToast();
  const role = auth.role();
  const [pendingAction, setPendingAction] = useState('');
  const pendingRef = useRef(false);
  const placementReviewRef = useRef(null);
  const runAction = async (key, action) => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPendingAction(key);
    try { await action(); } catch (error) {
      const blockers = error.details?.blockers;
      showError(blockers?.length ? `${error.message} ${blockers.join(' ')}` : error.message);
    } finally { pendingRef.current = false; setPendingAction(''); }
  };
  const [options, setOptions] = useState({ school_years: [], can_manage_placements: false, can_release: false });
  const [schoolYearId, setSchoolYearId] = useState('');
  const [grade, setGrade] = useState('');
  const [section, setSection] = useState('');
  const [term, setTerm] = useState('1');
  const [report, setReport] = useState(null);
  const [failedQuery, setFailedQuery] = useState('');
  const [comments, setComments] = useState({});
  const [learnerSearch, setLearnerSearch] = useState('');
  const [learnerFilter, setLearnerFilter] = useState('all');
  const [collapsedIds, setCollapsedIds] = useState({});
  const [placementSearch, setPlacementSearch] = useState('');
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
  const reportSections = useMemo(() => annexGReportSections(selectedYear), [selectedYear]);
  const grades = useMemo(() => [...new Set(reportSections.map((item) => item.grade))].sort((a, b) => Number(a) - Number(b)), [reportSections]);
  const selectedGrade = grades.includes(grade) ? grade : (grades[0] || '');
  const sections = reportSections.filter((item) => item.grade === selectedGrade);
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
      setSchoolYearId((current) => preferredAnnexGYear(result.school_years, current));
    } catch (error) { showError(error.message); }
  }, [showError]);
  useEffect(() => {
    let cancelled = false;
    api.get('/annex-g/options').then((result) => {
      if (cancelled) return;
      setOptions(result);
      setSchoolYearId((current) => preferredAnnexGYear(result.school_years, current));
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
      setCollapsedIds({});
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

  const preview = (learner) => {
    if (learner.placement_verified === false) {
      const query = new URLSearchParams({ school_year_id: schoolYearId, grade: selectedGrade, section: selectedSection, term_order: selectedTerm });
      return api.openDocument(`/annex-g/draft/${learner.person_id}/pdf?${query}`);
    }
    return api.openDocument(`/annex-g/preview/${learner.enrollment_id}/pdf?term_order=${selectedTerm}`);
  };
  const reviewEnrollment = (learner) => {
    const context = selectedYear.sections.find((item) => item.grade === selectedGrade && item.section === selectedSection);
    setReviewingPersonId(learner.person_id);
    setPlacementSearch('');
    setPlacementForm({ grade_level_id: String(context?.grade_level_id || ''), section_id: String(context?.id || ''), starts_on: '', confirmed: false });
    if (placementReviewRef.current) placementReviewRef.current.open = true;
    requestAnimationFrame(() => {
      const target = document.getElementById(`annex-g-placement-${learner.person_id}`);
      target?.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
      document.getElementById('annex-g-placement-start')?.focus({ preventScroll: true });
    });
  };
  const release = async (learner) => {
    try {
      const item = await api.post(`/annex-g/release/${learner.enrollment_id}?term_order=${selectedTerm}`, {});
      showSuccess(`Annex G released for ${learner.full_name}, Term ${selectedTerm}.`);
      await loadOptions();
      const query = new URLSearchParams({ school_year_id: schoolYearId, grade: selectedGrade, section: selectedSection, term_order: selectedTerm });
      setReport(await api.get(`/annex-g/section?${query}`));
      // A saved snapshot is downloaded separately; opening it must never create a release.
      return item;
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
      await loadOptions();
      if (selectionQuery) setReport(await api.get(`/annex-g/section?${selectionQuery}`));
    } catch (error) { showError(error.message); }
    finally { setSavingPlacementId(null); }
  };

  const allLearners = reportMatches ? report.learners : [];
  const readyCount = allLearners.filter((item) => item.blockers.length === 0).length;
  const attentionCount = allLearners.length - readyCount;
  const normalizedLearnerSearch = learnerSearch.trim().toLowerCase();
  const visibleLearners = allLearners.filter((learner) => {
    if (learnerFilter === 'ready' && learner.blockers.length > 0) return false;
    if (learnerFilter === 'attention' && learner.blockers.length === 0) return false;
    if (!normalizedLearnerSearch) return true;
    return `${learner.full_name} ${learner.lrn || ''}`.toLowerCase().includes(normalizedLearnerSearch);
  });
  const allCollapsed = visibleLearners.length > 0 && visibleLearners.every((learner) => collapsedIds[learner.enrollment_id]);
  const toggleAllLearners = () => {
    if (allCollapsed) {
      setCollapsedIds({});
    } else {
      setCollapsedIds(Object.fromEntries(visibleLearners.map((learner) => [learner.enrollment_id, true])));
    }
  };
  const normalizedPlacementSearch = placementSearch.trim().toLowerCase();
  const visibleCandidates = placementCandidates.filter((candidate) => {
    if (reviewingPersonId === candidate.id || !normalizedPlacementSearch) return true;
    return `${candidate.full_name} ${candidate.lrn || ''} ${candidate.current_section || ''}`.toLowerCase().includes(normalizedPlacementSearch);
  });

  return <section className="card-static annex-g-workspace">
    <div className="annex-g-header">
      <div>
        <p className="eyebrow">Grades 7–10 · Adviser draft &amp; records release</p>
        <h2>Annex G learner reports</h2>
        <p className="section-copy">Uses verified school-year enrollment, calculated age, finalized grades, and recorded attendance. Missing source data blocks release; this workspace never edits scores or attendance.</p>
      </div>
    </div>

    <div className="annex-g-filters">
      <label><span className="field-label">School year</span><select disabled={Boolean(pendingAction)} className="input-field" value={schoolYearId} onChange={(event) => { setSchoolYearId(event.target.value); setReviewingPersonId(null); setPlacementCandidates([]); setPlacementLoading(Boolean(event.target.value)); setPlacementError(''); setPlacementForm({ grade_level_id: '', section_id: '', starts_on: '', source_reference: '', confirmed: false }); }}><option value="">Choose school year</option>{years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
      <label><span className="field-label">Grade</span><select disabled={Boolean(pendingAction)} className="input-field" value={selectedGrade} onChange={(event) => setGrade(event.target.value)}><option value="">Choose grade</option>{grades.map((item) => <option key={item} value={item}>Grade {item}</option>)}</select></label>
      <label><span className="field-label">Section</span><select disabled={Boolean(pendingAction)} className="input-field" value={selectedSection} onChange={(event) => setSection(event.target.value)}><option value="">Choose section</option>{sections.map((item) => <option key={item.id} value={item.section}>{item.section} ({item.learner_count || 0} learners)</option>)}</select></label>
      <label><span className="field-label">Report term</span><select disabled={Boolean(pendingAction)} className="input-field" value={selectedTerm} onChange={(event) => setTerm(event.target.value)}>{(selectedYear?.terms || []).map((item) => <option key={item} value={item}>Term {item}</option>)}</select></label>
    </div>

    {reportMatches && <div className="annex-g-context">
      <div className="annex-g-context__item"><span className="annex-g-context__label">Class</span><strong>Grade {report.grade} · {report.section}</strong></div>
      <div className="annex-g-context__item"><span className="annex-g-context__label">Academic period</span><span>SY {report.school_year} · Term {report.term_order} ({report.term_name})</span></div>
      <div className="annex-g-context__item"><span className="annex-g-context__label">Adviser</span><span>{report.adviser_name || 'Not assigned'}</span></div>
      <div className="annex-g-context__item"><span className="annex-g-context__label">Age reference</span><span>{report.age_reference_date}</span></div>
      <div className="annex-g-context__item"><span className="annex-g-context__label">Readiness</span><span><strong>{readyCount}</strong> ready · <strong>{attentionCount}</strong> need attention</span></div>
    </div>}

    {loading && <p className="muted-small">Loading verified enrollment and term records…</p>}
    {!selectionQuery && <p className="empty-cell">No Grade 7–10 section is available for this account.</p>}
    {!loading && failedQuery === selectionQuery && selectionQuery && <p className="empty-cell">The report could not be loaded for this selection.</p>}

    {reportMatches && report.blockers?.length > 0 && <div className="annex-g-blockers annex-g-blockers--section">
      <strong>Section setup needs attention</strong>
      <ul>{report.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>}
    {reportMatches && report.unverified_learner_count > 0 && <p className="notice notice-blue">{report.unverified_learner_count} learner(s) are shown from saved class records. Their finalized term grades are available below. Verify enrollment before official release; draft attendance is left blank.</p>}

    {reportMatches && allLearners.length > 0 && <div className="annex-g-toolbar">
      <div className="annex-g-toolbar__filters" role="group" aria-label="Filter learners by readiness">
        <button type="button" className={learnerFilter === 'all' ? 'is-active' : ''} onClick={() => setLearnerFilter('all')}>All ({allLearners.length})</button>
        <button type="button" className={learnerFilter === 'ready' ? 'is-active' : ''} onClick={() => setLearnerFilter('ready')}>Ready ({readyCount})</button>
        <button type="button" className={learnerFilter === 'attention' ? 'is-active' : ''} onClick={() => setLearnerFilter('attention')}>Needs attention ({attentionCount})</button>
      </div>
      <div className="annex-g-toolbar__actions">
        <input type="search" className="input-field annex-g-search" placeholder="Search learner or LRN…" aria-label="Search learner by name or LRN" value={learnerSearch} onChange={(event) => setLearnerSearch(event.target.value)} />
        <button type="button" className="btn-secondary annex-g-collapse-btn" onClick={toggleAllLearners}>{allCollapsed ? 'Expand all' : 'Collapse all'}</button>
      </div>
    </div>}

    {reportMatches && <div className="annex-g-learners">
      {visibleLearners.length === 0 && <p className="empty-cell">No learners match the current filter.</p>}
      {visibleLearners.map((learner) => {
        const isCollapsed = Boolean(collapsedIds[learner.enrollment_id]);
        const learnerReleases = report.released_reports?.filter((item) => item.parameters.enrollment_id === learner.enrollment_id) || [];
        return <article className={`annex-g-learner${isCollapsed ? ' is-collapsed' : ''}`} key={learner.enrollment_id}>
          <div className="annex-g-learner-heading">
            <div className="annex-g-learner-identity">
              <h3>{learner.full_name}</h3>
              <p>LRN: {learner.lrn || 'Not recorded'} · Age: {learner.age ?? 'Missing'}{learner.placement_verified === false ? ' · Unverified placement' : ''}</p>
            </div>
            <div className="annex-g-learner-meta">
              <span className={learner.blockers.length ? 'tag tag-warning' : 'tag tag-success'}>
                {learner.blockers.length ? `${learner.blockers.length} item(s) to resolve` : 'Ready for review'}
              </span>
              <button type="button" className="btn-secondary annex-g-toggle-btn" aria-expanded={!isCollapsed} onClick={() => setCollapsedIds((current) => ({ ...current, [learner.enrollment_id]: !current[learner.enrollment_id] }))}>
                {isCollapsed ? 'Show details' : 'Hide details'}
              </button>
            </div>
          </div>

          {!isCollapsed && <>
            {learner.blockers.length > 0 && <div className="annex-g-blockers">
              <strong>Needs attention</strong>
              <ul>{learner.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>}

            <div className="table-scroll">
              <table className="interactive-table annex-g-grades-table">
                <colgroup>
                  <col className="col-area" />
                  <col className="col-term" />
                  <col className="col-term" />
                  <col className="col-term" />
                  <col className="col-final" />
                  <col className="col-remarks" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Learning area</th>
                    <th className="num-col">Term 1</th>
                    <th className="num-col">Term 2</th>
                    <th className="num-col">Term 3</th>
                    <th className="num-col">Final grade</th>
                    <th>Remarks</th>
                  </tr>
                </thead>
                <tbody>
                  {learner.learning_areas.map((area) => <FragmentRows key={area.name} area={area} />)}
                </tbody>
              </table>
            </div>

            {role === 'teacher' && learner.placement_verified !== false && <div className="annex-g-comment-box">
              <label>
                <span className="field-label">Term {selectedTerm} teacher comment / recommendation</span>
                <textarea className="input-field" rows="2" maxLength="2000" value={comments[learner.enrollment_id] || ''} onChange={(event) => setComments((current) => ({ ...current, [learner.enrollment_id]: event.target.value }))} />
              </label>
              <p className="muted-small">PDF previews include saved term comments. Save your changes before previewing or release.</p>
            </div>}
          </>}

          <div className="annex-g-learner-footer">
            <div className="annex-g-learner-notes">
              {learner.placement_verified === false && role === 'teacher' && <p className="muted-small">An administrator must verify this school-year enrollment before comments and official release are available.</p>}
              {learnerReleases.map((item) => <div className="annex-g-release-history" key={item.id}>
                <span>Released · {item.status} · {new Date(item.created_at).toLocaleString('en-PH')} · {item.generated_by_name}</span>
                <button type="button" className="btn-link" disabled={Boolean(pendingAction)} onClick={() => runAction(`download-${item.id}`, () => item.filename?.toLowerCase().endsWith('.pdf') ? api.download(`/annex-g/releases/${item.id}`, item.filename) : api.openDocument(`/annex-g/releases/${item.id}`))}>
                  {pendingAction === `download-${item.id}` ? 'Preparing…' : item.filename?.toLowerCase().endsWith('.pdf') ? 'Download PDF' : 'Open previous report'}
                </button>
              </div>)}
            </div>
            <div className="action-row">
              <button type="button" className="btn-secondary" disabled={Boolean(pendingAction)} onClick={() => runAction(`preview-${learner.enrollment_id}`, () => preview(learner))}>
                {pendingAction === `preview-${learner.enrollment_id}` ? 'Preparing PDF…' : 'Preview PDF'}
              </button>
              {role === 'teacher' && learner.placement_verified !== false && <button type="button" className="btn-primary" disabled={Boolean(pendingAction)} onClick={() => runAction(`comment-${learner.enrollment_id}`, () => saveComment(learner))}>
                {pendingAction === `comment-${learner.enrollment_id}` ? 'Saving…' : 'Save term comment'}
              </button>}
              {options.can_release && <button type="button" className="btn-primary" disabled={Boolean(pendingAction) || learner.placement_verified === false || learner.blockers.length > 0 || report.blockers.length > 0} onClick={() => runAction(`release-${learner.enrollment_id}`, () => release(learner))}>
                {pendingAction === `release-${learner.enrollment_id}` ? 'Releasing PDF…' : 'Release PDF'}
              </button>}
              {learner.placement_verified === false && options.can_manage_placements && <button type="button" className="btn-secondary" onClick={() => reviewEnrollment(learner)}>
                Verify enrollment
              </button>}
            </div>
          </div>
        </article>;
      })}
    </div>}

    {options.can_manage_placements && <details ref={placementReviewRef} className="annex-g-placement-review">
      <summary>
        <span>Review existing learner placements</span>
        <span className="annex-g-placement-count">{placementCandidates.length} unverified</span>
      </summary>
      <div className="annex-g-placement-body">
        <div className="annex-g-placement-toolbar">
          <p className="section-copy">For SY {selectedYear?.name || '—'}, choose each learner’s grade, section, and start date from a verified school record. Current profile details are shown only for context and are not treated as history. Missing dates of birth can be entered in Administration → People &amp; Records.</p>
          {placementCandidates.length > 5 && <input type="search" className="input-field annex-g-search" placeholder="Filter candidates…" aria-label="Filter placement candidates" value={placementSearch} onChange={(event) => setPlacementSearch(event.target.value)} />}
        </div>
        {placementLoading && <p className="muted-small">Loading learners without a placement…</p>}
        {placementError && <p className="notice notice-danger" role="alert">Learners could not be loaded: {placementError}</p>}
        {!placementLoading && !placementError && placementCandidates.length === 0 && <p className="empty-cell">All active learners already have a placement for this school year, or no student records are available.</p>}
        <div className="annex-g-placement-list">
          {visibleCandidates.map((candidate) => <article id={`annex-g-placement-${candidate.id}`} className="annex-g-placement-candidate" key={candidate.id}>
            <div className="annex-g-placement-heading">
              <div>
                <strong>{candidate.full_name}</strong>
                <span>LRN: {candidate.lrn || 'Not recorded'} · Current profile: {candidate.current_grade ? `Grade ${candidate.current_grade} · ${candidate.current_section || 'Section not set'}` : 'grade/section not set'} (context only)</span>
              </div>
              {reviewingPersonId !== candidate.id && <button type="button" className="btn-secondary" onClick={() => { setReviewingPersonId(candidate.id); setPlacementForm({ grade_level_id: '', section_id: '', starts_on: '', confirmed: false }); }}>Review placement</button>}
            </div>
            {reviewingPersonId === candidate.id && <div className="annex-g-placement-form">
              <div className="form-grid three-columns">
                <label><span className="field-label">Verified grade</span><select disabled={Boolean(pendingAction)} className="input-field" value={placementGrades.find((item) => selectedYear?.sections.find((sec) => sec.grade === item)?.grade_level_id === selectedPlacementGradeId) || ''} onChange={(event) => { const target = selectedYear?.sections.find((item) => item.grade === event.target.value); setPlacementForm((current) => ({ ...current, grade_level_id: String(target?.grade_level_id || ''), section_id: '' })); }} required><option value="">Choose grade</option>{placementGrades.map((item) => <option key={item} value={item}>Grade {item}</option>)}</select></label>
                <label><span className="field-label">Verified section</span><select className="input-field" value={placementForm.section_id} onChange={(event) => setPlacementForm((current) => ({ ...current, section_id: event.target.value }))} disabled={Boolean(pendingAction) || !placementForm.grade_level_id} required><option value="">Choose section</option>{placementSections.map((item) => <option key={item.id} value={item.id}>{item.section}</option>)}</select></label>
                <label><span className="field-label">Enrollment start date</span><input id="annex-g-placement-start" className="input-field" type="date" min={selectedYear?.starts_on || undefined} max={selectedYear?.ends_on || undefined} value={placementForm.starts_on} onChange={(event) => setPlacementForm((current) => ({ ...current, starts_on: event.target.value }))} required /></label>
              </div>
              <label className="checkbox-field"><input type="checkbox" checked={placementForm.confirmed} onChange={(event) => setPlacementForm((current) => ({ ...current, confirmed: event.target.checked }))} required /><span>I verified this learner’s placement and start date against an official school record.</span></label>
              <div className="action-row"><button type="button" className="btn-secondary" onClick={() => setReviewingPersonId(null)} disabled={savingPlacementId === candidate.id}>Cancel</button><button type="button" className="btn-primary" onClick={() => savePlacement(candidate)} disabled={savingPlacementId === candidate.id || !placementForm.grade_level_id || !placementForm.section_id || !placementForm.starts_on || !placementForm.confirmed}>{savingPlacementId === candidate.id ? 'Saving placement…' : 'Save verified placement'}</button></div>
            </div>}
          </article>)}
        </div>
      </div>
    </details>}
  </section>;
}

function FragmentRows({ area }) {
  return <>
    <tr>
      <th>{area.name}</th>
      {[1, 2, 3].map((number) => <td key={number} className="num-col">{area.term_grades?.[number] ?? '—'}</td>)}
      <td className="num-col final-col">{area.final_grade ?? '—'}</td>
      <td>{area.remarks || '—'}</td>
    </tr>
    {area.subareas?.map((subarea) => <tr className="table-subrow" key={subarea.name}>
      <td className="subarea-name">{subarea.name}</td>
      {[1, 2, 3].map((number) => <td key={number} className="num-col">{subarea.term_grades?.[number] ?? '—'}</td>)}
      <td className="num-col final-col">{subarea.final_grade ?? '—'}</td>
      <td>{subarea.descriptor || '—'}</td>
    </tr>)}
  </>;
}
